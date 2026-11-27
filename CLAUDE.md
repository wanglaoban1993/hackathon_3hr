# Team [TEAM NAME TBD]
Project: **Smart Buy Agent**: "Should I buy this now?" (AI Agents Berlin hackathon, submit by 19:45)

## The brief
**Nebius "Evidence to Action"** (primary) + **idealo** (if one project may enter both; ask at the Build Desk).
Build an agent that turns evidence into a decision. A *live* Nebius Token Factory model call must make the decision: no hardcoded if/else, no OpenAI/Claude models in the product.
Our version: user gives product + budget, idealo MCP offers are the evidence, and the Nebius model answers **BUY_NOW / WAIT / AVOID** with confidence, reasons, cited offers, conflicts found and next step.

## How we're judged
Nebius: Token Factory use **35**, Usefulness **30**, Handling uncertainty **25**, Clarity **10**.
Must deliver: runnable demo, a note naming the exact Token Factory model IDs + where the call decides (`MODEL_NOTE.md`), proof of calls (`nebius_calls.log`), routine case + incomplete/conflicting case.

## Our demo
1. **Routine**: "Sony WH-1000XM5, budget €300". Trusted merchants at ~€279, in stock → BUY_NOW, cites merchant.
2. **Conflicting**: unknown shop at €149 with no delivery date → flagged as too good to be true → AVOID that offer, recommend the best safe one.
Shown in a Streamlit UI (teammate 3).

## Rules
- **Don't add features. Ask first.** Build only what's listed here.
- Secrets live only in `.env` (git-ignored). Never print, log or commit the API key.
- Python calls the idealo MCP; the model never calls tools. Python pre-flags issues, the model decides.

## Build facts
- Windows/PowerShell, venv `.venv` (`.venv\Scripts\python.exe`). Deps in `requirements.txt`.
- Nebius: OpenAI SDK, `base_url=https://api.tokenfactory.nebius.com/v1/`, model from `NEBIUS_MODEL` in `.env` = `deepseek-ai/DeepSeek-V4.1-Flash-1017` (tested; Llama 3.3 not available; run `list_models.py`).
- Files: `nebius_client.py` (client), `agent.py` (`decide()`), `cases.py` (mock cases), `run_demo.py`, `list_models.py`, `MODEL_NOTE.md`, `app.py` (Streamlit starter UI, tested), `UI_BRIEF.md` (handoff to UI teammate).
- Offer dict contract (idealo teammate must match): `merchant, price, in_stock, delivery, merchant_rating`.
- Team: me = Nebius decision engine; teammate 2 = idealo MCP + data; teammate 3 = Streamlit UI, pitch, submission.
