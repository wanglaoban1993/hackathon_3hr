# Smart Buy Agent: "Should I buy this now?"

An agent that decides whether to buy a product, based on live price, availability and
merchant data from the [idealo MCP server](https://github.com/idealo/mcp-server-guide).
A live model on **Nebius Token Factory** makes the decision: **BUY_NOW / WAIT / AVOID**,
with a confidence score, reasons, cited shops, conflicts found and a concrete next step.

This repo is built for two hackathon challenges:

| Challenge | How this project fits |
|---|---|
| **idealo** | Uses idealo's MCP in an unexpected way: not just price comparison, but spotting offers that look cheap and are not trustworthy. |
| **Evidence to Action (Nebius)** | idealo data is the *evidence*. A live Nebius model call reads it and decides the next step. No hard-coded rule picks the outcome or the shop. |

## Status

| Part | State |
|---|---|
| idealo data layer (`idealo_client.py`) | Done and tested against the live server |
| Two demo cases in `demo_cases/` | Done (one routine, one conflicting) |
| Nebius decision agent (`agent.py`, `nebius_client.py`) | Done. `decide(evidence, budget)` takes the idealo Evidence directly; tested live |
| Command-line runner (`run_live.py`) | Done. Runs the agent on any cached or freshly fetched product |
| Streamlit apps (`app.py`, `app_live.py`) | `app.py`: the two fixed demo cases. `app_live.py`: any cached product or a new idealo search |

## How it works

```
idealo MCP ──► idealo_client.py ──► Evidence ──► agent.precheck() ──► Nebius model ──► Decision
(live data)    fetch, clean, cache   (JSON,       flags facts only     decides         BUY_NOW / WAIT / AVOID
                                      no verdict)  (no decision)        (live call)     + reasons, conflicts, next step
```

1. **Evidence** (`idealo_client.py`): offers per shop (total price, shop rating, delivery),
   29-day price history, market stats and a list of `gaps`. It makes **no judgement**.
2. **Pre-check** (`agent.py`, plain Python): only *flags* facts, for example an offer far
   below the median, a low-rated or unknown shop, unknown delivery, an over-budget offer,
   a big price move, or a list price that does not match the offers.
3. **Decision** (`agent.py`, live Nebius call): the model weighs the evidence and the flags
   and returns the decision. The reply is validated against a schema; if it is invalid the
   model is asked once more.
4. **Proof**: every call is appended to `nebius_calls.log` (call ID, model, tokens, latency,
   full prompt and raw reply). The API key is never logged.

## Setup

Requires Python 3.10 or newer (the MCP SDK does not support 3.9). We use a conda environment:

```bash
conda create -n hackathon --override-channels -c conda-forge python=3.11
conda activate hackathon
pip install -r requirements.txt
```

In VS Code, run **Python: Select Interpreter** and choose the `hackathon` environment.

### Nebius API key (required for the decision step)

```bash
cp .env.example .env
```

Open `.env` and paste your key after `NEBIUS_API_KEY=` (no quotes). Get a key at
<https://tokenfactory.nebius.com/project/api-keys>. Optionally set `NEBIUS_MODEL`; the default
is `deepseek-ai/DeepSeek-V4.1-Flash-1017`.

> **Never put the real key in `.env.example`** (it is tracked by git). Only `.env` is git-ignored.

Check that the key works and see which models you can use:

```bash
python list_models.py
```

### idealo login (only for fetching new products)

The first fetch from idealo opens a browser tab for the login (OAuth). The token is stored in
`.idealo_auth.json` (git-ignored) and reused afterwards. The callback uses `localhost:6274`,
so that port must be free. You do **not** need this for the demo cases or cached products.

## Usage

### 1. The quickest demo: the two fixed cases

```bash
python run_demo.py            # prints both decisions to the terminal
streamlit run app.py          # simple UI for the two demo cases
```

Expected: the routine case (Samsung Odyssey G50F, budget 160 EUR) gives **BUY_NOW**; the
conflicting case (GigaByte M27UP Ice, budget 300 EUR) flags the cheap-but-untrustworthy shop.

### 2. Any product: command line

```bash
python run_live.py --list                          # products already in cache/
python run_live.py --cache DE_27-zoll-monitor_p6   # use a cached product (no idealo call)
python run_live.py --cache DE_dell-u2723qe --budget 700
python run_live.py "27 zoll monitor" --pick 3      # fetch from idealo, then decide
```

- `--budget` is in EUR. If you leave it out, it defaults to 110% of the median offer price.
- Each run makes exactly **one live Nebius call** (about 10 to 20 seconds).

### 3. Any product: Streamlit app

```bash
streamlit run app_live.py
```

1. In the sidebar choose **Cached idealo products** (free) or **New idealo search**
   (query, result number, country; uses the idealo API).
2. Adjust the **budget** if you like.
3. Click **Ask the agent**. The page shows the decision badge, confidence, next step, reasons,
   conflicts, the pre-check flags, and the model name and Nebius call ID. Shops the model
   cited are highlighted in the offers table.

### 4. Fetch idealo evidence only (no model)

```bash
# Find a product (1 API call). Shows how many offers each result has.
python idealo_client.py "27 zoll monitor" --search --available-only

# Fetch full evidence for result number N (about 5 API calls)
python idealo_client.py "27 zoll monitor" --pick 3

# Other options
python idealo_client.py "27 zoll monitor" --pick 3 --refresh   # ignore the cache
python idealo_client.py "27 zoll monitor" --country GB         # DE, AT, GB, FR, IT, ES
python idealo_client.py --list-cache
```

### 5. From Python

```python
from idealo_client import get_evidence
from agent import decide

evidence = get_evidence("27 zoll monitor", country="DE", pick=3)  # cached after the first call
d = decide(evidence, budget=170)

print(d.decision, d.confidence)            # BUY_NOW | WAIT | AVOID, 0 to 1
print(d.reasons, d.cited_offers)
print(d.conflicts_found, d.next_step)
print(d.model_used, d.nebius_call_id)      # proof the Nebius model decided
```

`decide` also accepts a plain dict (for example a cached `*.evidence.json` loaded with `json.load`).
`get_evidence` uses `asyncio.run` internally, so call it from synchronous code.

## The Decision output

| Field | Meaning |
|---|---|
| `decision` | `BUY_NOW`, `WAIT` or `AVOID` |
| `confidence` | 0 to 1; reflects evidence quality, lower when real conflicts exist |
| `reasons` | Why, citing concrete shops and numbers |
| `cited_offers` | Shop names the model refers to (only shops in the evidence) |
| `conflicts_found` | Real conflicts, for example a clearly cheaper offer from a weak shop |
| `next_step` | One concrete action (which shop and price, or what to confirm first) |
| `flags` | Pre-check facts computed by code before the model decided |
| `model_used`, `nebius_call_id` | Filled in by code, shown in the UI as proof |

## The Evidence schema

| Field | Meaning |
|---|---|
| `product_name`, `product_url`, `list_price` | The product and its "from" price on idealo |
| `total_offers_on_idealo` | How many offers idealo lists in total |
| `user_rating`, `user_review_count`, `test_grade` | Reviews and test results, when available |
| `pros`, `cons` | From idealo's product details |
| `offers[]` | One entry per shop (see below) |
| `price_history` | 29-day min, max, average, current price, percent change, confidence (0 to 1) |
| `market_stats` | Min, median and max total price over the fetched offers |
| `gaps[]` | Plain-language list of what is missing or limited |

Each entry in `offers[]`:

`shop`, `is_marketplace`, `price`, `shipping`, `total_price`, `shipping_known`,
`shop_rating`, `shop_rating_count`, `delivery_status`, `delivery_text`,
`delivery_earliest`, `delivery_latest`, `free_return_days`, `payment_methods`,
`freshness`, `url`.

`total_price` is price plus shipping. Fields idealo does not return are `null`; the
decision step must handle that.

## Demo cases

Both are real idealo data captured on 2026-11-27, stored in [demo_cases/](demo_cases/) and
loaded by `cases.py`.

### Routine: `routine_samsung_odyssey_g50f.json`

Samsung Odyssey G50F. Nine offers from 132.65 to 149.88 EUR. The "from" price, the
cheapest offer and the current price in the history all agree on 132.65. Every offer
has `SHORT` delivery and the price history is stable. Expected decision: **BUY_NOW**,
confidence about 0.9, no conflicts.

### Conflicting: `conflict_gigabyte_m27up.json`

GigaByte M27UP Ice. The cheapest offer (joybuy.de, 259.00 EUR) is about 15% below the
median, but that shop has a rating of only 2.32 from 171 reviews, lower than every
other shop. The price also fell 13% over the last 29 days. Two shops list the product
with status `UNKNOWN` and availability only from 9 December. The product has just 5
user reviews, so its 5.0 rating says little. Expected decision: **do not simply pick
the cheapest offer**; flag the conflicts, confidence about 0.78, recommend coolblue.de.

### More examples

`cache/` holds other fetched products. `DE_27-zoll-monitor_p6` (LG UltraGear) gives a
**WAIT** because the price is near its 29-day high and only 10 of 42 offers are visible.
`DE_dell-u2723qe` has no offers at all, which makes a good "no data" case.

## Limits of the free (Trial) idealo tier

- At most **10 offers per product**, and they are the cheapest ones. Amazon, eBay and
  Otto are removed by idealo on every tier, so you usually see 8 to 10 offers.
- **500 calls per day** and 3 requests per second. This is why everything is cached.
- Prices come from a snapshot. Offers carry a `freshness` timestamp; the cache does not
  expire, so say "snapshot" when demoing.
- Some products give numbers that do not match: for example the search "from" price,
  the history's current price and the cheapest fetched offer can differ. This is real
  data behaviour, not a parsing bug, and the decision step treats it as a signal.
- Docs and real responses differ in places (for example `nextOffset` can be `-1`, and
  delivery fields sit under `delivery`). The parser accepts both layouts.

## Project layout

```
idealo_client.py      idealo MCP client: OAuth, fetching, parsing, caching, CLI
nebius_client.py      Nebius Token Factory client (OpenAI SDK), reads the key from .env
agent.py              pre-check flags + decide(): the live Nebius decision call
run_live.py           CLI: run the agent on a cached or freshly fetched product
run_demo.py           CLI: run the two fixed demo cases
list_models.py        check the Nebius key and list available model IDs
app.py                Streamlit UI for the two fixed demo cases
app_live.py           Streamlit UI for any cached product or a new idealo search
cases.py              loads the two demo cases and their budgets
demo_cases/           the two fixed demo evidence files
cache/                raw API responses and parsed evidence (created on first run)
MODEL_NOTE.md         submission note: exact model ID and where the call decides
UI_BRIEF.md           handoff notes for the UI
nebius_calls.log      proof of every Nebius call (git-ignored; attach to the submission)
.env                  your API key (git-ignored, never commit)
.idealo_auth.json     idealo OAuth token (git-ignored, never commit)
requirements.txt      Python dependencies
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `NEBIUS_API_KEY is not set` | Create `.env` from `.env.example` and paste your key; make sure it is saved in this folder. |
| `ModuleNotFoundError: No module named 'mcp'` (or `dotenv`) | You are on the wrong Python. Activate the `hackathon` environment and run `pip install -r requirements.txt`. |
| Red "Import could not be resolved" squiggles in VS Code | Select the `hackathon` interpreter, then reload the window. |
| `conda: command not found` | Run `conda init zsh`, then open a new terminal. |
| idealo browser login hangs | Make sure port 6274 is free, then run again. Delete `.idealo_auth.json` to force a fresh login. |
| `idealo tool error: ...` | Read the message; a common cause is hitting the daily limit. Use cached products. |
| `Nebius model did not return a valid decision` | Rare. Run again; the full reply is in `nebius_calls.log`. Keep `max_tokens` at 4000 (the model reasons before answering). |
| The model ID is rejected | Run `python list_models.py` and set `NEBIUS_MODEL` in `.env` to an ID from the list. |
