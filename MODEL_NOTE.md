# Model note: Nebius Token Factory usage

## Models called
- `deepseek-ai/DeepSeek-V4.1-Flash-1017` (named exactly as listed in Token Factory). This model makes every decision.

## Where the call makes the decision
`agent.py` → `decide(evidence, budget)`:

1. **Evidence**: live idealo MCP data from `idealo_client.get_evidence()`: offers per shop (total price, shop rating and review count, delivery status), 29-day price history, market stats and data gaps.
2. **Pre-check (Python, no decision)**: `precheck()` only *flags* facts: offers well below the median, low-rated or unknown shops, unknown delivery, unknown shipping, over-budget offers, big price moves, list price vs offer mismatch, few product reviews, API gaps.
3. **Decision (live Nebius call)**: `client.chat.completions.create(...)` against `https://api.tokenfactory.nebius.com/v1/`. The model weighs the evidence and flags and returns **BUY_NOW / WAIT / AVOID** with confidence, reasons, cited shops, conflicts found and a next step. No hardcoded rule picks the outcome or the shop.
4. **Validation**: the reply is checked against a Pydantic schema. If it is invalid, the model is asked once more.

## Proof of calls
Every call is appended to `nebius_calls.log` (JSON lines): timestamp, call ID, requested and reported model, token usage (including reasoning tokens), latency, the full prompt and the raw response. The API key is never logged.

## Cases (real idealo data, `demo_cases/`)
- **Routine: Samsung Odyssey G50F, budget €160.** Nine consistent offers (€132.65-149.88), stable price → BUY_NOW, confidence ~0.9, no conflicts.
- **Conflicting: GigaByte M27UP Ice, budget €300.** The cheapest shop (joybuy.de, €259) has a 2.32/5 rating, two shops have unknown delivery, and the price fell 13% in 29 days → the model flags joybuy.de as a too-good-to-be-true trap, lowers confidence to ~0.78 and recommends coolblue.de (€279, 4.64/5, delivery by 28.11.).

Run: `python run_demo.py` or `streamlit run app.py`
