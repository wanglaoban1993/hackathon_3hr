"""The two required demo cases: real idealo evidence captured 2026-11-27 (see demo_cases/).

Each case = (evidence dict, budget in EUR). For live data instead:
    from idealo_client import get_evidence
    evidence = get_evidence("27 zoll monitor", country="DE", pick=3)
"""
import json
from pathlib import Path

DEMO_DIR = Path(__file__).with_name("demo_cases")


def load(name: str) -> dict:
    return json.loads((DEMO_DIR / name).read_text(encoding="utf-8"))


CASES = {
    # Samsung Odyssey G50F: 9 consistent offers €132.65-149.88, stable price -> expect BUY_NOW
    "routine": (load("routine_samsung_odyssey_g50f.json"), 160),
    # GigaByte M27UP Ice: cheapest shop (joybuy.de €259) has a 2.32 rating, price fell 13%,
    # two shops with UNKNOWN delivery, only 5 product reviews -> expect conflict flagged
    "conflicting": (load("conflict_gigabyte_m27up.json"), 300),
}
