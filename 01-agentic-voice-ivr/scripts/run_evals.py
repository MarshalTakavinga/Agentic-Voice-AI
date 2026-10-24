"""Run the conversation scenarios in-process and write evals/latest_report.md.

Usage: python scripts/run_evals.py [--fail-under 1.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.evals import load_scenarios, run_scenario, summarize  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-under", type=float, default=1.0)
    args = parser.parse_args()

    results = []
    for scenario in load_scenarios():
        service = create_app(Settings(log_level="WARNING")).state.service  # isolated state
        results.append(run_scenario(service, scenario))
    summary = summarize(results)

    lines = [
        "# Conversation eval report",
        "",
        "Synthetic scripted scenarios against the rules NLU and mock adapters. "
        "This measures designed behavior, not production performance.",
        "",
        "| Scenario | Result | Turns | Final status | Tasks completed |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| `{r.id}` | {'PASS' if r.passed else 'FAIL'} | {r.turns} | {r.status} "
            f"| {', '.join(r.completed_tasks) or '-'} |"
        )
    lines += ["", "```json", json.dumps(summary, indent=2), "```"]
    failures = [f"- `{r.id}`: {f}" for r in results for f in r.failures]
    if failures:
        lines += ["", "## Failures", *failures]
    report = "\n".join(lines) + "\n"
    (ROOT / "evals" / "latest_report.md").write_text(report)
    print(report)
    return 0 if summary["pass_rate"] >= args.fail_under else 1


if __name__ == "__main__":
    raise SystemExit(main())
