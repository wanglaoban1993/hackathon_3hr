"""idealo MCP client: turns idealo product data into a clean "evidence" bundle.

Usage (CLI):
    python idealo_client.py "27 inch monitor" --country DE
    python idealo_client.py "27 inch monitor" --refresh      # ignore cache
    python idealo_client.py --list-cache

Usage (from the agent code):
    from idealo_client import get_evidence
    evidence = get_evidence("27 inch monitor")      # cached after the first call
    evidence.model_dump_json(indent=2)               # feed this to the Nebius model

Notes
- idealo MCP uses OAuth in the browser. The first run opens a browser tab; the token
  is stored in .idealo_auth.json (git-ignored) and reused afterwards.
- Trial tier: 500 calls/day, 3 req/s, max 10 offers per product -> everything is cached
  in ./cache so repeated demo runs never touch the API.
- The raw tool responses are saved next to the parsed evidence, so field names that the
  docs do not pin down (deliveryStatus, freshness, ...) can be checked against reality.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import statistics
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator
from urllib.parse import parse_qs, urlparse

import httpx2
from mcp import Client
from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from pydantic import AnyUrl, BaseModel, Field

MCP_URL = "https://mcp.idealo.com/mcp"
CALLBACK_PORT = 6274  # same port idealo's README uses for Claude Code
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

HERE = Path(__file__).resolve().parent
AUTH_FILE = HERE / ".idealo_auth.json"
CACHE_DIR = HERE / "cache"
BACKUP_DIR = CACHE_DIR / "backups"


# --------------------------------------------------------------------------- #
# Evidence schema (this is what the decision agent will read)
# --------------------------------------------------------------------------- #
class Offer(BaseModel):
    shop: str | None = None
    is_marketplace: bool | None = None
    price: float | None = Field(default=None, description="Item price in local currency")
    shipping: float | None = Field(default=None, description="Cheapest shipping cost, if known")
    total_price: float | None = Field(
        default=None, description="price + shipping (shipping=0 if unknown)"
    )
    shipping_known: bool = False
    shop_rating: float | None = None
    shop_rating_count: int | None = None
    delivery_text: str | None = None
    delivery_status: str | None = None
    delivery_earliest: str | None = None
    delivery_latest: str | None = None
    free_return_days: int | None = None
    payment_methods: list[str] = []
    freshness: str | None = None
    url: str | None = None


class PriceHistory(BaseModel):
    period_days: int | None = None
    current: float | None = None
    min: float | None = None
    max: float | None = None
    avg: float | None = None
    change_percent: float | None = None
    lowest_price_date: str | None = None
    highest_price_date: str | None = None
    data_source_confidence: float | None = Field(
        default=None, description="0-1, how reliable the price history is"
    )
    total_data_points: int | None = None


class MarketStats(BaseModel):
    """Plain descriptive numbers over the offers we fetched. No judgement here."""

    offer_count: int
    min_total: float | None = None
    median_total: float | None = None
    max_total: float | None = None


class Evidence(BaseModel):
    query: str
    country: str
    currency: str
    product_name: str | None = None
    product_url: str | None = None
    list_price: float | None = Field(
        default=None, description="'From' price shown in search results"
    )
    total_offers_on_idealo: int | None = None
    user_rating: float | None = None
    user_review_count: int | None = None
    test_grade: str | None = None
    pros: list[str] = []
    cons: list[str] = []
    offers: list[Offer] = []
    offers_capped_by_trial_tier: bool = False
    price_history: PriceHistory | None = None
    market_stats: MarketStats | None = None
    gaps: list[str] = Field(
        default_factory=list,
        description="Things we could not obtain (missing fields, empty history, ...)",
    )


# --------------------------------------------------------------------------- #
# Small parsing helpers
# --------------------------------------------------------------------------- #
def parse_price(value: Any) -> float | None:
    """'999,00 €' -> 999.0 ; '1.299,00 €' -> 1299.0 ; '£999.99' -> 999.99 ; 99900 -> 99900.0"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d.,]", "", str(value))
    if not s:
        return None
    if "," in s and "." in s:
        # last separator is the decimal one
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    elif "." in s:
        head, _, tail = s.rpartition(".")
        if len(tail) == 3 and head:  # "1.299" -> thousands separator
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def currency_for(country: str) -> str:
    return "GBP" if country.upper() in ("GB", "UK") else "EUR"


def _dig(d: Any, *paths: str) -> Any:
    """Return the first non-None value found under any dotted path, e.g. 'shop.rating.avg'."""
    for path in paths:
        cur = d
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break
        if cur is not None:
            return cur
    return None


def _to_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_offer(raw: dict) -> Offer:
    price = parse_price(_dig(raw, "price"))
    shipping_raw = _dig(raw, "minShippingCost", "shippingCost")
    shipping = parse_price(shipping_raw)
    if shipping is None and _dig(raw, "hasAlwaysFreeShipping") is True:
        shipping = 0.0
    payments = _dig(raw, "payments") or []
    return Offer(
        shop=_dig(raw, "shop.name", "name", "shop.merchantName", "merchantName"),
        is_marketplace=_dig(raw, "shop.isMarketplace", "isMarketplace"),
        price=price,
        shipping=shipping,
        total_price=round(price + (shipping or 0.0), 2) if price is not None else None,
        shipping_known=shipping is not None,
        shop_rating=_to_float(_dig(raw, "shop.rating.avg", "rating.avg")),
        shop_rating_count=_to_int(_dig(raw, "shop.rating.count", "rating.count")),
        delivery_text=_dig(raw, "delivery.deliveryText", "deliveryText"),
        delivery_status=_dig(raw, "delivery.deliveryStatus", "deliveryStatus"),
        delivery_earliest=_dig(raw, "delivery.earlyDeliveryDate", "earlyDeliveryDate"),
        delivery_latest=_dig(raw, "delivery.lateDeliveryDate", "lateDeliveryDate"),
        free_return_days=_to_int(_dig(raw, "freeReturnDays")),
        payment_methods=[
            name
            for p in payments
            if isinstance(p, dict) and (name := p.get("name") or p.get("costCode"))
        ],
        freshness=_dig(raw, "freshness"),
        url=_dig(raw, "relocatorUrl", "url"),
    )


def tool_payload(result: Any) -> dict:
    """Extract the JSON object from an MCP CallToolResult."""
    if result.is_error:
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise RuntimeError(f"idealo tool error: {text[:500]}")
    if result.structured_content:
        return result.structured_content
    for c in result.content:
        text = getattr(c, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("idealo tool returned no JSON payload")


# --------------------------------------------------------------------------- #
# OAuth plumbing (browser login once, token cached on disk)
# --------------------------------------------------------------------------- #
class FileTokenStorage:
    def _read(self) -> dict:
        try:
            return json.loads(AUTH_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, key: str, value: dict) -> None:
        data = self._read()
        data[key] = value
        AUTH_FILE.write_text(json.dumps(data, indent=2))
        AUTH_FILE.chmod(0o600)

    async def get_tokens(self) -> OAuthToken | None:
        d = self._read().get("tokens")
        return OAuthToken.model_validate(d) if d else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write("tokens", tokens.model_dump(mode="json"))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        d = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(d) if d else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._write("client_info", client_info.model_dump(mode="json"))


async def _open_browser(url: str) -> None:
    print("\n[idealo] Opening browser for login. If nothing opens, visit:\n", url, "\n", flush=True)
    webbrowser.open(url)


async def _wait_for_callback() -> AuthorizationCodeResult:
    """Tiny one-shot HTTP server on localhost that captures ?code=...&state=..."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[AuthorizationCodeResult] = loop.create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = (await reader.readline()).decode("latin-1")
            while (await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass  # drain headers
            target = request_line.split(" ")[1] if " " in request_line else "/"
            qs = parse_qs(urlparse(target).query)
            ok = "code" in qs
            body = (
                "<h3>idealo login complete - you can close this tab.</h3>"
                if ok
                else f"<h3>Login failed: {qs.get('error', ['unknown'])[0]}</h3>"
            )
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
                + body.encode()
            )
            await writer.drain()
            if ok and not fut.done():
                fut.set_result(
                    AuthorizationCodeResult(
                        code=qs["code"][0],
                        state=qs.get("state", [None])[0],
                        iss=qs.get("iss", [None])[0],
                    )
                )
            elif not fut.done():
                fut.set_exception(RuntimeError(f"OAuth error: {qs}"))
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", CALLBACK_PORT)
    try:
        return await asyncio.wait_for(fut, timeout=300)
    finally:
        server.close()
        await server.wait_closed()


def _auth_provider() -> OAuthClientProvider:
    metadata = OAuthClientMetadata(
        client_name="hackathon-procurement-agent",
        redirect_uris=[AnyUrl(REDIRECT_URI)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
    )
    return OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=metadata,
        storage=FileTokenStorage(),
        redirect_handler=_open_browser,
        callback_handler=_wait_for_callback,
    )


@asynccontextmanager
async def connect() -> AsyncGenerator[Client]:
    """Connected, authenticated MCP client for the idealo server."""
    http = httpx2.AsyncClient(
        auth=_auth_provider(),
        timeout=httpx2.Timeout(30, read=300),
    )
    async with http:
        async with Client(streamable_http_client(MCP_URL, http_client=http)) as client:
            yield client


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
async def fetch_raw(
    query: str,
    country: str = "DE",
    pick: int = 0,
    max_offers: int = 10,
    filters: dict | None = None,
) -> dict:
    """Call the idealo tools and return all raw responses (also useful to inspect real fields)."""
    raw: dict[str, Any] = {"query": query, "country": country}
    async with connect() as client:
        args: dict[str, Any] = {"query": query, "country": country}
        if filters:
            args["filters"] = filters
        search = tool_payload(await client.call_tool("search_products", args))
        raw["search"] = search
        results = search.get("results") or []
        if not results:
            return raw
        product = results[min(pick, len(results) - 1)]
        raw["picked"] = product
        ref = product["productRef"]
        common = {"productRef": ref, "country": country}

        raw["details"] = tool_payload(await client.call_tool("get_product_details", common))

        offers: list[dict] = []
        pages: list[dict] = []
        offset = 0
        while len(offers) < max_offers:
            page_args = dict(common)
            if offset:
                page_args["offset"] = offset
            page = tool_payload(await client.call_tool("get_product_offers", page_args))
            pages.append(page)
            offers.extend(page.get("offers") or [])
            offset = _to_int(page.get("nextOffset")) or 0
            if offset <= 0:  # docs say 0 = done; the server also returns -1 on some products
                break
            await asyncio.sleep(0.4)  # stay well under 3 req/s
        raw["offers_pages"] = pages
        raw["offers"] = offers[:max_offers]

        await asyncio.sleep(0.4)
        raw["price_history"] = tool_payload(
            await client.call_tool("get_product_price_history", common)
        )
    return raw


def build_evidence(raw: dict) -> Evidence:
    country = raw["country"]
    picked = raw.get("picked") or {}
    details = raw.get("details") or {}
    gaps: list[str] = []

    if not picked:
        return Evidence(
            query=raw["query"],
            country=country,
            currency=currency_for(country),
            gaps=["search returned no products"],
        )

    offers = [parse_offer(o) for o in raw.get("offers") or []]
    if not offers:
        gaps.append("no offers returned")
    if offers and not any(o.shop_rating is not None for o in offers):
        gaps.append("shop ratings not available in the offer data")
    if offers and not any(o.shipping_known for o in offers):
        gaps.append("shipping costs not available; total_price equals item price")
    elif any(not o.shipping_known for o in offers):
        gaps.append("shipping cost unknown for some offers; their total_price excludes shipping")

    last_page = (raw.get("offers_pages") or [{}])[-1]
    capped = bool(last_page.get("message"))
    if capped:
        gaps.append(f"offer list truncated by API tier: {last_page['message']}")

    ph_raw = (raw.get("price_history") or {})
    trend = ph_raw.get("priceTrend")
    history = None
    if trend:
        st = trend.get("statistics") or {}
        # periodDays / dataSourceConfidence / totalDataPoints live inside priceTrend
        # (docs list them at top level); accept both.
        meta = {**ph_raw, **trend}
        history = PriceHistory(
            period_days=_to_int(meta.get("periodDays")),
            current=parse_price(st.get("currentPrice")),
            min=parse_price(st.get("minPrice")),
            max=parse_price(st.get("maxPrice")),
            avg=parse_price(st.get("avgPrice")),
            change_percent=_to_float(st.get("priceChangePercent")),
            lowest_price_date=st.get("lowestPriceDate"),
            highest_price_date=st.get("highestPriceDate"),
            data_source_confidence=_to_float(meta.get("dataSourceConfidence")),
            total_data_points=_to_int(meta.get("totalDataPoints")),
        )
    else:
        gaps.append("no price history available")

    totals = [o.total_price for o in offers if o.total_price is not None]
    stats = (
        MarketStats(
            offer_count=len(offers),
            min_total=min(totals),
            median_total=statistics.median(totals),
            max_total=max(totals),
        )
        if totals
        else None
    )

    reviews = picked.get("userReviewsSummary") or {}
    tests = picked.get("testReportsSummary") or {}
    pros_cons = details.get("prosCons") or {}
    return Evidence(
        query=raw["query"],
        country=country,
        currency=currency_for(country),
        product_name=picked.get("name") or details.get("name"),
        product_url=picked.get("url") or details.get("url"),
        list_price=parse_price(picked.get("price")),
        total_offers_on_idealo=_to_int(picked.get("totalOfferCount")),
        user_rating=_to_float(reviews.get("averageRating")),
        user_review_count=_to_int(reviews.get("totalReviewCount")),
        test_grade=tests.get("grade"),
        pros=pros_cons.get("pros") or [],
        cons=pros_cons.get("cons") or [],
        offers=offers,
        offers_capped_by_trial_tier=capped,
        price_history=history,
        market_stats=stats,
        gaps=gaps,
    )


# --------------------------------------------------------------------------- #
# Cache + public entry points
# --------------------------------------------------------------------------- #
def _slug(query: str, country: str) -> str:
    return f"{country.upper()}_{re.sub(r'[^a-z0-9]+', '-', query.lower()).strip('-')}"


def _backup_existing(*files: Path) -> Path | None:
    """Copy existing cache files to cache/backups/ with a timestamp before they are overwritten.

    Returns the backup folder, or None if there was nothing to back up.
    """
    existing = [f for f in files if f.exists()]
    if not existing:
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in existing:
        # DE_x.raw.json -> DE_x.raw.20261127-171500.json
        stem, _, ext = f.name.rpartition(".")
        shutil.copy2(f, BACKUP_DIR / f"{stem}.{stamp}.{ext}")
    return BACKUP_DIR


def get_evidence(
    query: str,
    country: str = "DE",
    pick: int = 0,
    refresh: bool = False,
    filters: dict | None = None,
) -> Evidence:
    """Cached evidence for a product query. Hits the API only when no cache file exists."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = _slug(query, country) + (f"_p{pick}" if pick else "")
    raw_file = CACHE_DIR / f"{key}.raw.json"
    evidence_file = CACHE_DIR / f"{key}.evidence.json"
    if raw_file.exists() and not refresh:
        raw = json.loads(raw_file.read_text())
    else:
        # Fetch first: if the API call fails, the existing files stay untouched.
        raw = asyncio.run(fetch_raw(query, country, pick=pick, filters=filters))
        backup_dir = _backup_existing(raw_file, evidence_file)
        if backup_dir:
            print(f"[cache] previous files backed up to {backup_dir}/")
        raw_file.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    evidence = build_evidence(raw)
    evidence_file.write_text(evidence.model_dump_json(indent=2, exclude_none=True))
    return evidence


def print_summary(e: Evidence) -> None:
    print(f"\n{e.product_name}  ({e.country}, {e.currency})")
    print(f"  from-price: {e.list_price}   offers on idealo: {e.total_offers_on_idealo}")
    if e.market_stats:
        s = e.market_stats
        print(f"  fetched {s.offer_count} offers; total price min/median/max: "
              f"{s.min_total} / {s.median_total} / {s.max_total}")
    if e.price_history:
        h = e.price_history
        chg = f"{h.change_percent:.1f}%" if h.change_percent is not None else "n/a"
        print(f"  {h.period_days or '?'}d history: min {h.min}  avg {h.avg}  max {h.max}  "
              f"current {h.current}  (change {chg})")
    print("\n  shop                      total   rating(n)      delivery")
    for o in sorted(e.offers, key=lambda x: x.total_price or 1e12):
        rating = f"{o.shop_rating}({o.shop_rating_count})" if o.shop_rating is not None else "-"
        total = f"{o.total_price:.2f}" if o.total_price is not None else "-"
        print(f"  {str(o.shop)[:24]:24} {total:>8}  {rating:14} "
              f"{o.delivery_status or ''} {o.delivery_text or ''}")
    for g in e.gaps:
        print(f"  ! gap: {g}")


async def _search_only(query: str, country: str, available_only: bool) -> list[dict]:
    async with connect() as client:
        args: dict[str, Any] = {"query": query, "country": country}
        if available_only:
            args["filters"] = {"availableOnly": True}
        return (tool_payload(await client.call_tool("search_products", args))).get("results") or []


def list_search(query: str, country: str, available_only: bool) -> None:
    """One API call: show search hits so you can pick a product with many offers (use --pick N)."""
    results = asyncio.run(_search_only(query, country, available_only))
    print(f"\n{len(results)} results for {query!r} ({country})")
    print("  #  offers  from-price   reviews        type     name")
    for i, r in enumerate(results):
        rv = r.get("userReviewsSummary") or {}
        rev = f"{rv.get('averageRating')}({rv.get('totalReviewCount')})" if rv else "-"
        print(f"  {i:<2} {r.get('totalOfferCount')!s:>6}  {r.get('price')!s:>10}  {rev:13}  "
              f"{r.get('itemType', ''):8} {str(r.get('name'))[:60]}")
    print("\nPick one with: python idealo_client.py QUERY --pick N")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("query", nargs="?")
    ap.add_argument("--country", default="DE")
    ap.add_argument("--pick", type=int, default=0, help="which search result to use (0 = first)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache and call the API")
    ap.add_argument("--list-cache", action="store_true")
    ap.add_argument("--search", action="store_true", help="only list search results (1 API call)")
    ap.add_argument("--available-only", action="store_true", help="with --search: in-stock only")
    args = ap.parse_args()

    if args.list_cache:
        for p in sorted(CACHE_DIR.glob("*.evidence.json")):
            print(p.name)
        return
    if not args.query:
        ap.error("query is required")
    if args.search:
        list_search(args.query, args.country, args.available_only)
        return
    evidence = get_evidence(args.query, args.country, pick=args.pick, refresh=args.refresh)
    print_summary(evidence)
    print(f"\nSaved to {CACHE_DIR}/ (look at *.raw.json to see the real API fields)")


if __name__ == "__main__":
    main()
