# Model note: Nebius Token Factory usage

## Models called
- `deepseek-ai/DeepSeek-V4.1-Flash-1017` (named exactly as listed in Token Factory). This model makes every decision.

## Where the call makes the decision
`agent.py` → `decide(product, budget, offers)`:

1. **Evidence**: offers from idealo (merchant, price, in_stock, delivery, merchant_rating).
2. **Pre-check (Python, no decision)**: `precheck()` only *flags* issues: price outliers vs. the median, missing delivery time, unknown or low-rated merchants, over-budget or out-of-stock offers.
3. **Decision (live Nebius call)**: `client.chat.completions.create(...)` against `https://api.tokenfactory.nebius.com/v1/`. The model reads the offers and flags, then returns **BUY_NOW / WAIT / AVOID** with confidence, reasons, cited offers, conflicts found and a next step. No hardcoded rule picks the outcome.
4. **Validation**: the reply is checked against a Pydantic schema. If it is invalid, the model is asked once more.

## Proof of calls
Every call is appended to `nebius_calls.log` (JSON lines): timestamp, call ID, requested and reported model, token usage, latency, the full prompt and the raw response. The API key is never logged.

## Cases
- **Routine** (`cases.py`): three trusted, consistent offers → BUY_NOW, confidence ~0.90.
- **Conflicting**: adds an unknown shop at €149 (47% below the median, no delivery date, no rating) → the model flags it, lowers confidence to ~0.78 and recommends the safe offer instead.

Run: `python run_demo.py`
