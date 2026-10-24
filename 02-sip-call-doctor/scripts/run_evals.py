"""Evaluate detection on labeled captures; writes evals/latest_report.md.

Usage: python scripts/run_evals.py [--fail-under 1.0]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sipdoc.evals import evaluate  # noqa: E402
from sipdoc.observability import configure_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fail-under", type=float, default=1.0, help="minimum fraction of captures matched exactly"
    )
    args = parser.parse_args()
    configure_logging("WARNING")
    r = evaluate()

    lines = [
        "# Detection eval report",
        "",
        "Synthetic labeled captures. Measures designed behavior, not accuracy on real traffic.",
        "",
        f"**Exact matches:** {r['exact_matches']}/{r['captures']} · "
        f"**Root-cause accuracy:** {r['root_cause_accuracy']:.0%} · "
        f"**False positives:** {r['false_positives']} · "
        f"**False negatives:** {r['false_negatives']}",
        "",
        "| Capture | Expected | Found | Root cause | Result |",
        "|---|---|---|---|---|",
    ]
    for row in r["rows"]:
        lines.append(
            f"| `{row['capture']}` | {', '.join(row['expected']) or '—'} | "
            f"{', '.join(row['found']) or '—'} | {row['root_cause'] or '—'} | "
            f"{'PASS' if row['exact'] else 'FAIL'} |"
        )
    lines += ["", "| Signature | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|"]
    for name, s in r["signatures"].items():
        fmt = lambda v: "—" if v is None else f"{v:.2f}"  # noqa: E731
        lines.append(
            f"| `{name}` | {s['tp']} | {s['fp']} | {s['fn']} | {fmt(s['precision'])} | "
            f"{fmt(s['recall'])} |"
        )
    report = "\n".join(lines) + "\n"
    (ROOT / "evals" / "latest_report.md").write_text(report)
    print(report)
    return 0 if r["exact_matches"] / r["captures"] >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
