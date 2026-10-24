"""Prompt-injection evaluation; writes evals/injection_report.md.

python scripts/run_injection_evals.py          # compromised-model mode (free, runs in CI)
python scripts/run_injection_evals.py --live   # real Claude; needs IVR_ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.adapters.mock import MockCustomerSystem  # noqa: E402
from app.config import DEFAULT_DATA_DIR  # noqa: E402
from app.injection_evals import load_attacks, run_attack, summarize  # noqa: E402
from app.observability import configure_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="send attacks to real Claude")
    parser.add_argument("--model", default="claude-haiku-5-5")
    args = parser.parse_args()
    configure_logging("WARNING")

    client = None
    if args.live:
        key = os.environ.get("IVR_ANTHROPIC_API_KEY", "")
        if not key:
            print("Set IVR_ANTHROPIC_API_KEY for --live mode.", file=sys.stderr)
            return 2
        from app.agent.planner import AnthropicClient

        client = AnthropicClient(key, args.model)

    results = [run_attack(a, MockCustomerSystem(DEFAULT_DATA_DIR), client) for a in load_attacks()]
    s = summarize(results)
    mode = (
        f"live: {args.model}"
        if args.live
        else "compromised model (attacker controls every model output)"
    )
    lines = [
        "# Prompt-injection report",
        "",
        f"Mode: **{mode}**",
        "",
        f"**{s['passed']}/{s['attacks']} attacks contained** · unauthorized tool successes: "
        f"**{s['unauthorized_tool_successes']}** · forbidden content spoken: "
        f"**{s['forbidden_content_spoken']}**",
        "",
        "| Attack | Result | Model called | Refused tool calls | What the caller heard |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        refused = ", ".join(r["refused_tools"]) or "none"
        heard = r["reply"].replace("|", "\\|")
        lines.append(
            f"| `{r['id']}` | {'CONTAINED' if r['passed'] else 'FAILED'} | "
            f"{'yes' if r['model_called'] else 'no'} | {refused} | {heard} |"
        )
    failures = [f"- `{r['id']}`: {f}" for r in results for f in r["failures"]]
    if failures:
        lines += ["", "## Failures", *failures]
    report = "\n".join(lines) + "\n"
    name = "injection_report_live.md" if args.live else "injection_report.md"
    (ROOT / "evals" / name).write_text(report)
    print(report)
    return 0 if s["passed"] == s["attacks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
