# Procurement Evidence Agent: idealo data layer

An agent that decides whether a team should buy a product, based on live price,
availability and merchant data from the [idealo MCP server](https://github.com/idealo/mcp-server-guide).

This repo is built for two hackathon challenges:

| Challenge | How this project fits |
|---|---|
| **idealo** | Uses idealo's MCP in an unexpected way: not just price comparison, but spotting offers that look cheap and are not trustworthy. |
| **Evidence to Action (Nebius)** | idealo data is the *evidence*. A live Nebius model call reads it and decides the next step: buy, wait, escalate, or ask for more information. |

## Status

| Part | State |
|---|---|
| idealo data layer (`idealo_client.py`) | Done and tested against the live server |
| Two demo cases in `demo_cases/` | Done (one routine, one conflicting) |
| Nebius decision agent (`agent.py`, `nebius_client.py`) | Done and tested live on mock offers (`cases.py`). Not yet wired to the idealo Evidence schema |
| Streamlit demo UI (`app.py`) | Starter works; see `UI_BRIEF.md` |

## How it works

```
idealo MCP  ──►  idealo_client.py  ──►  Evidence (JSON)  ──►  Nebius model  ──►  decision + reasons
 (live data)     fetch, clean, cache     facts only, no          (to be built)    each reason cites
                                         judgement                                an offer
```

The data layer deliberately makes **no judgement**. It reports facts such as the
total price (item plus shipping), shop ratings, delivery status, 29-day price
history, and a list of `gaps` (data it could not get). Deciding whether a low
price is a bargain or a trap is left to the model, so the decision is a real
live model call and not a hard-coded rule.

## Setup

Requires Python 3.10 or newer (the MCP SDK does not support 3.9). We use a conda environment:

```bash
conda create -n hackathon --override-channels -c conda-forge python=3.11
conda activate hackathon
pip install -r requirements.txt
```

In VS Code, run **Python: Select Interpreter** and choose the `hackathon` environment.

## Usage

### Command line

```bash
# 1. Find a product (1 API call). Shows how many offers each result has.
python idealo_client.py "27 zoll monitor" --search --available-only

# 2. Fetch full evidence for result number N (about 5 API calls)
python idealo_client.py "27 zoll monitor" --pick 3

# 3. Other options
python idealo_client.py "27 zoll monitor" --pick 3 --refresh   # ignore the cache
python idealo_client.py "27 zoll monitor" --country GB         # DE, AT, GB, FR, IT, ES
python idealo_client.py --list-cache
```

**First run:** a browser tab opens for the idealo login (OAuth). The token is stored in
`.idealo_auth.json` (git-ignored) and reused afterwards. The callback uses
`localhost:6274`, so that port must be free.

### From Python

```python
from idealo_client import get_evidence

evidence = get_evidence("27 zoll monitor", country="DE", pick=3)
print(evidence.model_dump_json(indent=2, exclude_none=True))   # feed this to the model
```

`get_evidence` reads from `cache/` when a cached copy exists, so repeated calls are free.
Note that it uses `asyncio.run` internally, so call it from synchronous code.

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

Both are real idealo data captured on 2026-11-27, stored in [demo_cases/](demo_cases/).

### Routine: `routine_samsung_odyssey_g50f.json`

Samsung Odyssey G50F. Nine offers from 132.65 to 149.88 EUR. The "from" price, the
cheapest offer and the current price in the history all agree on 132.65. Every offer
has `SHORT` delivery and the price history is stable. Expected decision: **buy**, with
a clear cheapest option.

### Conflicting: `conflict_gigabyte_m27up.json`

GigaByte M27UP Ice. The cheapest offer (joybuy.de, 259.00 EUR) is about 15% below the
median, but that shop has a rating of only 2.32 from 171 reviews, lower than every
other shop. The price also fell 13% over the last 29 days. Two shops list the product
with status `UNKNOWN` and availability only from 9 December. The product has just 5
user reviews, so its 5.0 rating says little. Expected decision: **do not simply pick
the cheapest offer**; flag the conflict and say what to confirm first.

## Limits of the free (Trial) idealo tier

- At most **10 offers per product**, and they are the cheapest ones. Amazon, eBay and
  Otto are removed by idealo on every tier, so you usually see 8 to 10 offers.
- **500 calls per day** and 3 requests per second. This is why everything is cached.
- Prices come from a snapshot. Offers carry a `freshness` timestamp; the cache does not
  expire, so say "snapshot" when demoing.
- Some products give numbers that do not match: for example the search "from" price,
  the history's current price and the cheapest fetched offer can differ. This is real
  data behaviour, not a parsing bug, and the decision step should treat it as a signal.
- Docs and real responses differ in places (for example `nextOffset` can be `-1`, and
  delivery fields sit under `delivery`). The parser accepts both layouts.

## Project layout

```
idealo_client.py      MCP client, OAuth, fetching, parsing, caching, CLI
demo_cases/           the two fixed demo evidence files
cache/                raw API responses and parsed evidence (created on first run)
requirements.txt      Python dependencies
.idealo_auth.json     OAuth token (created on first login, never commit)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'mcp'` | You are on the wrong Python. Use the `hackathon` environment (3.10+). |
| Red "Import could not be resolved" squiggles in VS Code | Select the `hackathon` interpreter, then reload the window. |
| `conda: command not found` | Run `conda init zsh`, then open a new terminal. |
| Browser login hangs | Make sure port 6274 is free, then run again. Delete `.idealo_auth.json` to force a fresh login. |
| `idealo tool error: ...` | Read the message; a common cause is hitting the daily limit. Use cached data. |
