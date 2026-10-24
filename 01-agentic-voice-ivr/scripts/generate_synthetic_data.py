"""Generate deterministic synthetic customers and outages. No real people or accounts.

Usage: python scripts/generate_synthetic_data.py
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.adapters.mock import hash_pin  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "synthetic"
rng = random.Random(20261024)  # fixed seed: reproducible fixtures

FIRST = ["Ava", "Ben", "Chloe", "Dmitri", "Esi", "Farid", "Grace", "Hiro", "Ines", "Jamal"]
LAST = ["Martinez", "Okafor", "Nguyen", "Petrov", "Mensah", "Haddad", "Kim", "Sato", "Silva"]
ZIPS = ["73301", "60614", "98101", "02139", "85004"]
PLANS = ["Fiber 300", "Fiber 1 Gig", "Fiber 2 Gig"]

# Documented fixtures used by tests, evals and the README demo.
FIXED = [
    ("10000001", "1234", "Ava", "Martinez", "73301", 8999, False),
    ("10000002", "4321", "Ben", "Okafor", "60614", 4250, False),
    ("10000099", "9999", "Fault", "Injection", "98101", 1000, True),
]


def salt() -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(32))


def customer(i, account, pin, first, last, zip_code, cents, fault):
    s = salt()
    return {
        "customer_id": f"C{i:05d}",
        "account_number": account,
        "first_name": first,
        "last_name": last,
        "service_zip": zip_code,
        "plan": rng.choice(PLANS),
        "balance_cents": cents,
        "due_date": (date(2026, 11, 1) + timedelta(days=rng.randint(0, 20))).isoformat(),
        "pin_salt": s,
        "pin_hash": hash_pin(pin, s),
        "simulate_fault": fault,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [customer(i + 1, *f) for i, f in enumerate(FIXED)]
    for i in range(len(FIXED), 25):
        rows.append(
            customer(
                i + 1,
                f"{10000100 + i}",
                f"{rng.randint(0, 9999):04d}",
                rng.choice(FIRST),
                rng.choice(LAST),
                rng.choice(ZIPS),
                rng.randint(0, 25000),
                False,
            )
        )
    outages = [
        {
            "zip": "73301",
            "active": True,
            "description": "A fiber cut is affecting internet service in your area",
            "eta": datetime(2026, 10, 24, 18, 0).isoformat(),
        },
        {"zip": "98101", "active": False, "description": "Resolved maintenance", "eta": None},
    ]
    (OUT / "customers.json").write_text(json.dumps(rows, indent=2) + "\n")
    (OUT / "outages.json").write_text(json.dumps(outages, indent=2) + "\n")
    print(f"wrote {len(rows)} customers, {len(outages)} outages to {OUT}")


if __name__ == "__main__":
    main()
