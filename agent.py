"""Smart Buy Agent: decision engine.

decide(product, budget, offers) -> Decision

Python only *pre-flags* evidence issues (outliers, missing data, over budget).
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

# Pre-check thresholds (flags only; the model decides what they mean)
OUTLIER_BELOW_MEDIAN = 0.70   # price < 70% of median -> suspicious
MIN_TRUSTED_RATING = 4.0      # merchant rating out of 5


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


SYSTEM_PROMPT = """You are a careful shopping decision agent. You decide whether the user should buy a product now.

You receive: the product, the user's budget in EUR, a list of offers (merchant, price, in_stock, delivery, merchant_rating), and pre-check flags computed by code.

Decide exactly one:
- BUY_NOW: at least one trustworthy, in-stock offer within budget with clear delivery. Recommend the best such offer.
- WAIT: evidence is incomplete or too uncertain to act safely (e.g. no trustworthy in-stock offer within budget, key data missing).
- AVOID: the offers that look attractive are suspicious or unsafe and no safe alternative exists within budget.

Rules:
- Use ONLY the evidence given. Never invent merchants, prices, or delivery times.
- Cite offers by exact merchant name in cited_offers (only merchants that appear in the evidence).
- A price far below the others, an unknown/unrated merchant, or "in stock" with no delivery date is a conflict: list each in conflicts_found and do NOT recommend that offer.
- If a suspicious offer exists but a safe offer within budget also exists, you may still decide BUY_NOW for the safe offer; say clearly which offer to avoid.
- Confidence must reflect evidence quality, not just how good the best offer is. If ANY conflict or precheck flag exists, confidence must be clearly lower than for clean, consistent evidence (clean evidence ~0.9; with conflicts at most ~0.8, lower the more serious or numerous they are). Say what is missing or uncertain.
- next_step: one concrete action for the user.

Return ONLY a JSON object, no other text:
{"decision": "BUY_NOW|WAIT|AVOID", "confidence": 0.0-1.0, "reasons": [str], "cited_offers": [str], "conflicts_found": [str], "next_step": str}"""


def precheck(offers: list[dict], budget: float) -> list[str]:
    """Flag evidence problems. Does NOT decide anything."""
    flags = []
    if not offers:
        return ["No offers found."]

    prices = [o["price"] for o in offers if isinstance(o.get("price"), (int, float))]
    median = round(statistics.median(prices), 2) if prices else None

    for o in offers:
        name = o.get("merchant") or "<unnamed merchant>"
        price = o.get("price")
        if price is None:
            flags.append(f"{name}: price missing.")
        else:
            if median and len(prices) >= 3 and price < OUTLIER_BELOW_MEDIAN * median:
                flags.append(f"{name}: price €{price} is {round(100 * (1 - price / median))}% below the median €{median} (possible too-good-to-be-true).")
            if price > budget:
                flags.append(f"{name}: price €{price} is over budget (€{budget}).")
        if not o.get("in_stock"):
            flags.append(f"{name}: not in stock.")
        elif not o.get("delivery"):
            flags.append(f"{name}: says in stock but gives no delivery time.")
        rating = o.get("merchant_rating")
        if rating is None:
            flags.append(f"{name}: no merchant rating (unknown merchant).")
        elif rating < MIN_TRUSTED_RATING:
            flags.append(f"{name}: low merchant rating {rating}/5.")
    return flags


def _log(entry: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def decide(product: str, budget: float, offers: list[dict], max_attempts: int = 2) -> Decision:
    client, model = get_client(), get_model()
    flags = precheck(offers, budget)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(
            {"product": product, "budget_eur": budget, "offers": offers, "precheck_flags": flags},
            ensure_ascii=False)},
    ]

    last_error = None
    for attempt in range(1, max_attempts + 1):
        t0 = time.time()
        resp = client.chat.completions.create(model=model, temperature=0, max_tokens=1000, messages=messages)
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
            "product": product,
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
