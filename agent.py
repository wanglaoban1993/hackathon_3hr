"""Smart Buy Agent: decision engine.

decide(evidence, budget=None) -> Decision

`evidence` is the idealo Evidence (from idealo_client.get_evidence() or a demo_cases/*.json file),
as a pydantic model or dict.

Python only *pre-flags* evidence issues (price outliers, weak shops, unknown delivery, gaps...).
The final BUY_NOW / WAIT / AVOID decision is made by a live Nebius Token Factory call.
Every call is appended to nebius_calls.log (JSON lines) as proof of usage.
"""
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from nebius_client import get_client, get_model

LOG_PATH = Path(__file__).with_name("nebius_calls.log")

# Pre-check thresholds: these only raise flags; the model decides what they mean
CHEAP_VS_MEDIAN = 0.90          # total price >10% below the median of fetched offers
LOW_SHOP_RATING = 3.5           # idealo shop rating (out of 5)
FEW_SHOP_REVIEWS = 50
FEW_PRODUCT_REVIEWS = 10
BIG_PRICE_MOVE_PCT = 10         # 29-day price change, in percent
LIST_PRICE_MISMATCH = 0.02      # idealo "from" price vs cheapest fetched offer

# Offer fields sent to the model (drops URLs, payment lists etc. to save tokens)
OFFER_FIELDS = ["shop", "total_price", "price", "shipping", "shipping_known", "shop_rating",
                "shop_rating_count", "delivery_status", "delivery_text", "is_marketplace", "free_return_days"]


class Decision(BaseModel):
    decision: Literal["BUY_NOW", "WAIT", "AVOID"]
    confidence: float = Field(ge=0, le=1)
    reasons: list[str]
    cited_offers: list[str]
    conflicts_found: list[str]
    next_step: str
    # Filled in by code, not the model, for transparency in the UI / note
    model_used: str = ""
    nebius_call_id: str = ""
    flags: list[str] = []


SYSTEM_PROMPT = """You are a careful purchasing decision agent. You decide whether the user should buy a product now, and from which shop.

You receive live idealo evidence: the product, the user's budget in EUR (may be null), offers from shops (total_price = price + shipping, shop_rating out of 5 with review count, delivery_status SHORT/MEDIUM/LONG/UNKNOWN, delivery_text), a 29-day price history, market stats, data gaps, and pre-check flags computed by code.

Decide exactly one:
- BUY_NOW: at least one trustworthy offer (solid shop rating, known delivery) within budget. Recommend the best such offer; it does not have to be the cheapest.
- WAIT: evidence is incomplete or too uncertain to act safely, or the price situation suggests waiting.
- AVOID: the attractive offers are untrustworthy and no safe alternative exists within budget.

Rules:
- Use ONLY the evidence given. Never invent shops, prices, ratings or delivery dates.
- Cite offers by exact shop name in cited_offers (only shops that appear in the evidence).
- The cheapest offer is not automatically the best. A price clearly below the others combined with a weak shop rating, or unknown delivery, is a conflict: list each conflict in conflicts_found, explain the trade-off, and do not recommend that offer without saying what to verify.
- Also treat inconsistencies between sources (list price vs offers, price history moves, very few product reviews, data gaps) as conflicts or uncertainty worth stating.
- Distinguish real conflicts from background caveats. Background caveats apply to almost every product (offer list capped by the API tier, few product reviews, a low-rated shop that is NOT cheaper than the trustworthy offers, small normal price differences). Mention them in reasons, but do NOT list them in conflicts_found and let them lower confidence only slightly. Real conflicts (ALWAYS list these, even if you recommend a different offer): a clearly cheaper offer from a weak or unknown shop (a "too good to be true" trap), sources disagree, delivery of a relevant offer is unknown, big price moves, nothing safe within budget.
- Confidence must reflect evidence quality, not just how good the best offer is. Consistent evidence with only background caveats: ~0.85-0.95. With real conflicts: clearly lower (at most ~0.8), lower the more serious or numerous they are. Say what is missing or uncertain.
- next_step: one concrete action, naming the shop and total price if buying, or what exactly to confirm first.

Return ONLY a JSON object, no other text:
{"decision": "BUY_NOW|WAIT|AVOID", "confidence": 0.0-1.0, "reasons": [str], "cited_offers": [str], "conflicts_found": [str], "next_step": str}"""


def _as_dict(evidence) -> dict:
    if hasattr(evidence, "model_dump"):
        return evidence.model_dump(exclude_none=True)
    return dict(evidence)


def _total(o: dict) -> Optional[float]:
    t = o.get("total_price")
    return t if isinstance(t, (int, float)) else o.get("price")


def precheck(ev: dict, budget: Optional[float] = None) -> list[str]:
    """Flag evidence problems. Does NOT decide anything."""
    flags: list[str] = []
    offers = ev.get("offers") or []
    if not offers:
        return ["No offers found."] + list(ev.get("gaps") or [])

    totals = [t for t in (_total(o) for o in offers) if t is not None]
    median = (ev.get("market_stats") or {}).get("median_total") or (statistics.median(totals) if totals else None)
    cheapest = min(totals) if totals else None
    ratings = [o["shop_rating"] for o in offers if o.get("shop_rating") is not None]

    for o in offers:
        name = o.get("shop") or "<unnamed shop>"
        total, rating = _total(o), o.get("shop_rating")
        if total is None:
            flags.append(f"{name}: price missing.")
        else:
            if median and total < CHEAP_VS_MEDIAN * median:
                flags.append(f"{name}: €{total:.2f} is {round(100 * (1 - total / median))}% below the median €{median:.2f}.")
            if budget is not None and total > budget:
                flags.append(f"{name}: €{total:.2f} is over budget (€{budget}).")
        if rating is None:
            flags.append(f"{name}: no shop rating (unknown shop).")
        elif rating < LOW_SHOP_RATING:
            lowest = " (lowest of all shops)" if ratings and rating == min(ratings) else ""
            flags.append(f"{name}: low shop rating {rating}/5{lowest}.")
        if o.get("shop_rating_count") is not None and o["shop_rating_count"] < FEW_SHOP_REVIEWS:
            flags.append(f"{name}: only {o['shop_rating_count']} shop reviews.")
        status = o.get("delivery_status")
        if not status or status == "UNKNOWN":
            flags.append(f"{name}: delivery uncertain ({o.get('delivery_text') or 'no delivery info'}).")
        if o.get("shipping_known") is False:
            flags.append(f"{name}: shipping cost unknown, total price may be higher.")
        if o.get("is_marketplace"):
            flags.append(f"{name}: marketplace seller.")

    ph = ev.get("price_history") or {}
    if ph.get("change_percent") is not None and abs(ph["change_percent"]) >= BIG_PRICE_MOVE_PCT:
        flags.append(f"Price moved {ph['change_percent']:+.0f}% over {ph.get('period_days', '?')} days "
                     f"(min €{ph.get('min')}, avg €{ph.get('avg')}, max €{ph.get('max')}).")
    lp = ev.get("list_price")
    if lp and cheapest and abs(lp - cheapest) / cheapest > LIST_PRICE_MISMATCH:
        flags.append(f"idealo 'from' price €{lp} differs from cheapest fetched offer €{cheapest:.2f}.")
    if ev.get("user_review_count") is not None and ev["user_review_count"] < FEW_PRODUCT_REVIEWS:
        flags.append(f"Product has only {ev['user_review_count']} user reviews; its rating says little.")
    if budget is not None and totals and cheapest > budget:
        flags.append(f"No offer is within budget (cheapest €{cheapest:.2f}).")
    flags += [f"Data gap: {g}" for g in ev.get("gaps") or []]
    return flags


def model_input(ev: dict, budget: Optional[float], flags: list[str]) -> dict:
    """The compact evidence the model sees."""
    return {
        "product": ev.get("product_name") or ev.get("query"),
        "budget_eur": budget,
        "currency": ev.get("currency", "EUR"),
        "idealo_list_price": ev.get("list_price"),
        "product_user_rating": ev.get("user_rating"),
        "product_user_review_count": ev.get("user_review_count"),
        "total_offers_on_idealo": ev.get("total_offers_on_idealo"),
        "offers": [{k: o.get(k) for k in OFFER_FIELDS if o.get(k) is not None} for o in ev.get("offers") or []],
        "price_history": ev.get("price_history"),
        "market_stats": ev.get("market_stats"),
        "gaps": ev.get("gaps") or [],
        "precheck_flags": flags,
    }


def _log(entry: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def decide(evidence, budget: Optional[float] = None, max_attempts: int = 2) -> Decision:
    ev = _as_dict(evidence)
    client, model = get_client(), get_model()
    flags = precheck(ev, budget)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(model_input(ev, budget, flags), ensure_ascii=False)},
    ]

    last_error = None
    for attempt in range(1, max_attempts + 1):
        t0 = time.time()
        resp = client.chat.completions.create(model=model, temperature=0, max_tokens=4000, messages=messages)  # model reasons before answering; leave room
        text = resp.choices[0].message.content or ""
        usage = resp.usage.model_dump() if resp.usage else None

        try:
            result = Decision.model_validate_json(_extract_json(text))
            last_error = None
        except ValidationError as e:
            result, last_error = None, str(e)

        _log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "call_id": resp.id,
            "model_requested": model,
            "model_reported": resp.model,
            "attempt": attempt,
            "latency_s": round(time.time() - t0, 2),
            "usage": usage,
            "product": ev.get("product_name") or ev.get("query"),
            "request_messages": messages,
            "response_text": text,
            "parsed_ok": result is not None,
        })

        if result is not None:
            result.model_used = resp.model or model
            result.nebius_call_id = resp.id
            result.flags = flags
            return result

        # Retry once, telling the model what was wrong
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": f"Your reply was not valid JSON for the required schema: {last_error[:500]}. Return ONLY the JSON object."},
        ]

    raise RuntimeError(f"Nebius model did not return a valid decision after {max_attempts} attempts: {last_error}")
