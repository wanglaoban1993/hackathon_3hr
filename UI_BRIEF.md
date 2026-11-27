# Smart Buy Agent: brief for the UI teammate

**What we're building:** "Should I buy this now?" The user picks a product and budget, the agent looks at idealo offers, and a **live Nebius model** decides **BUY_NOW / WAIT / AVOID** with reasons, conflicts and a next step. Your part: the Streamlit UI, the pitch and the submission. Code freeze 19:15, submit 19:45.

## 1. Setup (5 min)
```powershell
cd smart-buy-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Open `.env` and paste the Nebius key after `NEBIUS_API_KEY=` (no quotes). Get the key from me by DM, or make your own at tokenfactory.nebius.com/project/api-keys. **Never commit `.env` or post the key in the group chat.**

Check it works:
```powershell
python list_models.py   # should list models; we use deepseek-ai/DeepSeek-V4.1-Flash-1017
python run_demo.py      # runs both demo cases in the terminal
streamlit run app.py    # opens the starter UI in the browser
```

## 2. Your starting point: `app.py` (already works)
Pick a demo case → see the offers table → click **Ask the agent** → decision, confidence bar, next step, reasons, conflict warnings, and "Decided by <model> on Nebius" at the bottom. Build on this file.

## 3. The only function you need
```python
from agent import decide
d = decide(product, budget, offers)   # one live Nebius call, takes ~2-5 s, so show a spinner
```
`offers` = list of dicts: `merchant, price, in_stock, delivery, merchant_rating` (see `cases.py`).

What `d` contains:
| Field | Type | Show it as |
|---|---|---|
| `decision` | `"BUY_NOW"` / `"WAIT"` / `"AVOID"` | big coloured badge (green / orange / red) |
| `confidence` | float 0-1 | progress bar or % |
| `next_step` | str | highlighted box: the main takeaway |
| `reasons` | list[str] | bullet list |
| `conflicts_found` | list[str] | warning boxes (key for the conflicting case) |
| `cited_offers` | list[str] | highlight these merchants in the offers table |
| `flags` | list[str] | optional: what our Python pre-check spotted before the model |
| `model_used`, `nebius_call_id` | str | **always visible**: proves the Nebius call |

## 4. What the judges look for (design the UI around this)
Nebius scoring: **Token Factory use 35**, Usefulness 30, **Handling uncertainty 25**, Clarity 10.
- Make it obvious the **Nebius model** made the decision (model name + call ID on screen).
- In the conflicting case, make the **⚠️ suspicious €149 offer** and the lower confidence stand out next to the safe recommendation.

## 5. Demo script (2 cases)
1. **Routine**: Sony WH-1000XM5, €300 budget → BUY_NOW ~90%, buy from Amazon €281.99.
2. **Conflicting**: same, plus cheap-deals24.biz at €149 with no delivery date and no rating → still recommends Amazon, but flags the €149 shop as too good to be true, and confidence drops to ~78%.

## 6. Submission checklist
- [ ] Runnable demo (`streamlit run app.py`)
- [ ] `MODEL_NOTE.md`: models used + where the decision happens (done)
- [ ] `nebius_calls.log`: proof of calls (created automatically when you run it; attach it to the submission)
- [ ] Both cases shown

## Rules
- **Don't add features. Ask first.** Don't edit `agent.py` / `nebius_client.py`; ask me if you need a change.
- Real idealo data will replace the mock offers in `cases.py` later; the UI doesn't need to change.
