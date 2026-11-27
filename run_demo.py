"""Run both required cases against the live Nebius model."""
from agent import decide
from cases import CASES

for name, (evidence, budget) in CASES.items():
    print(f"\n=== {name.upper()} CASE: {evidence.get('product_name')}, budget €{budget}, "
          f"{len(evidence.get('offers', []))} idealo offers ===")
    d = decide(evidence, budget)
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

print("\nEvery call is logged in nebius_calls.log")
