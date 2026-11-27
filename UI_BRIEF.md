# Smart Buy Agent: brief for the UI teammate

**What we're building:** "Should I buy this now?" The agent reads **live idealo evidence** (shops, prices, ratings, delivery, price history), and a **live Nebius model** decides **BUY_NOW / WAIT / AVOID** with reasons, conflicts and a next step. Your part: the Streamlit UI, the pitch and the submission. Code freeze 19:15, submit 19:45.

## 1. Setup (5 min)
```powershell
git clone https://github.com/RanaPrince/hackathon_3hr.git
cd hackathon_3hr
python -m venv .venv
.venv\Scripts\activate        # Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # Mac: cp .env.example .env
```
Open `.env` and paste the Nebius key after `NEBIUS_API_KEY=` (no quotes). Get it from me by DM, or make your own at tokenfactory.nebius.com/project/api-keys. **Never commit `.env` or post the key in the group chat.**

Check it works:
```powershell
python list_models.py   # lists models; we use deepseek-ai/DeepSeek-V4.1-Flash-1017
python run_demo.py      # runs both demo cases in the terminal (~10-20 s each)
streamlit run app.py    # opens the starter UI in the browser
```

## 2. Your starting point: `app.py` (already works)
Pick a case → product metrics (price, 29-day trend, reviews) + offers table → **Ask the agent** → decision badge, confidence bar, next step, reasons, conflict warnings, cited shops highlighted in the table, pre-check flags, and "Decided by <model> on Nebius" at the bottom. Build on this file.

## 3. The only function you need
```python
from agent import decide
from cases import CASES                 # {"routine": (evidence, budget), "conflicting": (...)}
evidence, budget = CASES["conflicting"]
d = decide(evidence, budget)            # one live Nebius call, ~10-20 s, so show a spinner
```
`evidence` is idealo's Evidence (dict from `demo_cases/*.json`, or `idealo_client.get_evidence(...)` for live data).

What `d` contains:
| Field | Type | Show it as |
|---|---|---|
| `decision` | `"BUY_NOW"` / `"WAIT"` / `"AVOID"` | big coloured badge (green / orange / red) |
| `confidence` | float 0-1 | progress bar or % |
| `next_step` | str | highlighted box: the main takeaway |
| `reasons` | list[str] | bullet list |
| `conflicts_found` | list[str] | warning boxes (key for the conflicting case) |
| `cited_offers` | list[str] (shop names) | highlight these shops in the offers table |
| `flags` | list[str] | optional: what our Python pre-check spotted before the model |
| `model_used`, `nebius_call_id` | str | **always visible**: proves the Nebius call |

## 4. What the judges look for (design the UI around this)
Nebius scoring: **Token Factory use 35**, Usefulness 30, **Handling uncertainty 25**, Clarity 10.
- Make it obvious the **Nebius model** made the decision (model name + call ID on screen).
- In the conflicting case, make the **⚠️ cheap but untrustworthy joybuy.de offer** and the lower confidence stand out next to the safe recommendation.

## 5. Demo script (2 cases, real idealo data)
1. **Routine**: Samsung Odyssey G50F, €160 budget → BUY_NOW ~0.9, no conflicts; recommends a solid shop at ~€133-143.
2. **Conflicting**: GigaByte M27UP Ice, €300 budget → still BUY_NOW but ~0.78: **skips the cheapest offer** (joybuy.de €259, rating 2.32/5), flags it as too good to be true plus two shops with unknown delivery and a 13% price drop, and recommends coolblue.de at €279 (4.64/5).

The model's wording (and sometimes which of two similar shops it picks) varies a little between runs. That's expected with a live model.

## 6. Submission checklist
- [ ] Runnable demo (`streamlit run app.py`)
- [ ] `MODEL_NOTE.md`: models used + where the decision happens (done)
- [ ] `nebius_calls.log`: proof of calls (created automatically when you run it; attach it to the submission, it's git-ignored)
- [ ] Both cases shown

## Rules
- **Don't add features. Ask first.** Don't edit `agent.py` / `nebius_client.py`; ask me if you need a change.
