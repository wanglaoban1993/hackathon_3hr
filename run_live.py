"""Run the Nebius decision agent on idealo evidence (cached or live).

    python run_live.py --list                         # cached products
    python run_live.py --cache DE_27-zoll-monitor_p6  # use a cached product (no idealo API call)
    python run_live.py "27 zoll monitor" --pick 3     # fetch from idealo (cached after first time)
    python run_live.py --cache DE_dell-u2723qe --budget 700

Budget defaults to 110% of the median offer price. Each run makes ONE live Nebius call.
"""
import argparse
import json
import math
from pathlib import Path

from agent import Decision, decide

CACHE_DIR = Path(__file__).with_name("cache")


def list_cached() -> dict[str, dict]:
    """{cache key: evidence dict} for every parsed evidence file in cache/."""
    out = {}
    for f in sorted(CACHE_DIR.glob("*.evidence.json")):
        out[f.name.removesuffix(".evidence.json")] = json.loads(f.read_text(encoding="utf-8"))
    return out


def default_budget(evidence: dict) -> int:
    """110% of the median total price, rounded up to the next 10 EUR (0 if there are no offers)."""
    median = (evidence.get("market_stats") or {}).get("median_total")
    return int(math.ceil(median * 1.1 / 10) * 10) if median else 0


def print_decision(evidence: dict, budget: float, d: Decision) -> None:
    print(f"\n=== {evidence.get('product_name')} | budget €{budget} | "
          f"{len(evidence.get('offers', []))} offers ===")
    print(f"Decision:   {d.decision}  (confidence {d.confidence:.2f})")
    print(f"Model:      {d.model_used}  [call {d.nebius_call_id}]")
    print("Pre-check flags:" + ("" if d.flags else " none"))
    for f in d.flags:
        print(f"  - {f}")
    print("Reasons:")
    for r in d.reasons:
        print(f"  - {r}")
    print(f"Cited offers: {', '.join(d.cited_offers) or '-'}")
    print("Conflicts found:" + ("" if d.conflicts_found else " none"))
    for c in d.conflicts_found:
        print(f"  - {c}")
    print(f"Next step:  {d.next_step}")
    print("\nCall logged in nebius_calls.log")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="?", help="idealo search query (fetches live if not cached)")
    p.add_argument("--pick", type=int, default=0, help="search result number (see idealo_client.py --search)")
    p.add_argument("--country", default="DE")
    p.add_argument("--cache", help="cache key of an already fetched product (see --list)")
    p.add_argument("--budget", type=float, help="budget in EUR")
    p.add_argument("--list", action="store_true", help="list cached products and exit")
    a = p.parse_args()

    if a.list:
        for key, ev in list_cached().items():
            print(f"{key:40s} {ev.get('product_name')}  ({len(ev.get('offers', []))} offers)")
        return

    if a.cache:
        evidence = list_cached().get(a.cache)
        if evidence is None:
            p.error(f"no cached product '{a.cache}'; run with --list")
    elif a.query:
        from idealo_client import get_evidence  # imported lazily: needs the mcp package + idealo login
        evidence = get_evidence(a.query, country=a.country, pick=a.pick).model_dump(exclude_none=True)
    else:
        p.error("give a query or --cache KEY (or --list)")

    budget = a.budget if a.budget is not None else default_budget(evidence)
    print_decision(evidence, budget, decide(evidence, budget or None))


if __name__ == "__main__":
    main()
