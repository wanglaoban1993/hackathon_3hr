# Team [TEAM NAME TBD]
Project: **Smart Buy Agent**: "Should I buy this now?" (AI Agents Berlin hackathon, submit by 19:45)

## The brief
**Nebius "Evidence to Action"** (primary) + **idealo** (if one project may enter both; ask at the Build Desk).
Build an agent that turns evidence into a decision. A *live* Nebius Token Factory model call must make the decision: no hardcoded if/else, no OpenAI/Claude models in the product.
Our version: user gives product + budget, idealo MCP offers are the evidence, and the Nebius model answers **BUY_NOW / WAIT / AVOID** with confidence, reasons, cited offers, conflicts found and next step.

## How we're judged
Nebius: Token Factory use **35**, Usefulness **30**, Handling uncertainty **25**, Clarity **10**.
Must deliver: runnable demo, a note naming the exact Token Factory model IDs + where the call decides (`MODEL_NOTE.md`), proof of calls (`nebius_calls.log`), routine case + incomplete/conflicting case.

## Our demo (real idealo data in `demo_cases/`, loaded by `cases.py`)
1. **Routine**: Samsung Odyssey G50F, budget €160 → BUY_NOW ~0.9, no conflicts.
2. **Conflicting**: GigaByte M27UP Ice, budget €300 → cheapest shop joybuy.de (€259, rating 2.32) flagged as a trap, plus unknown-delivery shops and a 13% price drop → confidence ~0.78, recommends coolblue.de €279.
Shown in a Streamlit UI (teammate 3).

## Rules
- **Don't add features. Ask first.** Build only what's listed here.
- Secrets live only in `.env` (git-ignored). Never print, log or commit the API key.
- Python calls the idealo MCP; the model never calls tools. Python pre-flags issues, the model decides.

## Build facts
- Windows/PowerShell, venv `.venv` (`.venv\Scripts\python.exe`). Deps in `requirements.txt`.
- Nebius: OpenAI SDK, `base_url=https://api.tokenfactory.nebius.com/v1/`, model from `NEBIUS_MODEL` in `.env` = `deepseek-ai/DeepSeek-V4.1-Flash-1017` (tested; Llama 3.3 not available; run `list_models.py`).
- Files: `nebius_client.py` (client), `agent.py` (`decide()`), `cases.py` (mock cases), `run_demo.py`, `list_models.py`, `MODEL_NOTE.md`, `app.py` (Streamlit starter UI, tested), `UI_BRIEF.md` (handoff to UI teammate).
- `decide(evidence, budget)` takes idealo's `Evidence` (from `idealo_client.py`) as model or dict. Offers use `shop, total_price, shop_rating, shop_rating_count, delivery_status, delivery_text...`.
- The model reasons before answering (reasoning tokens), so `max_tokens` must stay high (4000); 1200 truncated replies.
- idealo client needs OAuth (`.idealo_auth.json`, git-ignored) and the `mcp` package (Python 3.10+).
- Team: me = Nebius decision engine; teammate 2 = idealo MCP + data; teammate 3 = Streamlit UI, pitch, submission.
