"""Markdown reports: readable in a pull request, a CI summary, or on GitHub."""

from __future__ import annotations

from typing import Any

from vae.noise import PROFILES
from vae.runner import RunResult

CAVEAT = (
    "Synthetic scripted scenarios against the target named above. These numbers measure designed "
    "behavior on these inputs; they are not production containment, accuracy or latency figures. "
    "Text-level ASR noise approximates recognizer output; it is not audio-level testing."
)


def _fmt(v: Any) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.1%}" if 0 <= v <= 1 else f"{v:,.2f}"
    return str(v)


def _ms(v: Any) -> str:
    return "–" if v is None else f"{v:,.1f}"


def _row(*cells: object) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render(run: RunResult, max_failures: int = 40) -> str:
    s = run.summary
    lines = [
        f"# Voice agent eval report: `{run.suite}`",
        "",
        " · ".join(
            [
                f"Target `{run.target}`",
                f"suite `{run.fingerprint}`",
                f"vae {run.vae_version}",
                run.started_at,
                f"seed {run.seed}",
                f"concurrency {run.concurrency}",
                f"repeats {run.repeats}",
                f"isolation {run.isolation}",
            ]
        ),
        "",
        f"> {CAVEAT}",
        "",
    ]
    if run.gates:
        overall = "PASS" if all(g["result"] != "fail" for g in run.gates) else "FAIL"
        lines += [
            "## Gates: " + overall,
            "",
            "| Gate | Threshold | Measured | Result |",
            "|---|---|---|---|",
        ]
        icon = {"pass": "✅ pass", "fail": "❌ fail", "skipped": "⚪ skipped"}
        for g in run.gates:
            actual = g["actual"]
            shown = _ms(actual) if "latency" in g["gate"] else _fmt(actual)
            lines.append(f"| {g['gate']} | {g['threshold']} | {shown} | {icon[g['result']]} |")
        lines.append("")

    lat = s["latency"]
    esc = s["escalation"]
    lines += [
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Calls run | {s['runs']} ({s['scenarios']} distinct scenarios) |",
        f"| Pass rate, clean + injection | {_fmt(s['pass_rate'])} |",
        f"| Task completion (clean scenarios with tasks) | {_fmt(s['task_completion_rate'])} |",
        f"| Avg turns to complete | {_fmt(s['avg_turns_to_complete'])} |",
        f"| Benign ASR-noise robustness | {_fmt(s['benign_robustness'])} |",
        f"| Stress ASR-noise robustness (not gated) | {_fmt(s['stress_robustness'])} |",
        f"| Safety under corrupted identifiers | {_fmt(s['corrupting_safety'])} |",
        _row(
            "Unauthorized tool calls",
            f"{s['unauthorized_tool_calls']} of {s['tool_successes']} successful tool calls",
        ),
        f"| Disclosures of forbidden content | {s['disclosures']} |",
        _row(
            "Escalation: correct / missed / unneeded",
            f"{esc['correct_escalations']} / {esc['missed_escalations']} / "
            f"{esc['unneeded_escalations']}",
        ),
        f"| Target errors | {s['errors']} ({_fmt(s['error_rate'])}) |",
        _row(
            "Turn latency p50 / p95 / p99 (client, ms)",
            f"{_ms(lat['p50_ms'])} / {_ms(lat['p95_ms'])} / {_ms(lat['p99_ms'])} "
            f"over {lat['turns']} turns",
        ),
        f"| Flaky scenarios across repeats | {len(s['flaky'])} |",
        _row(
            "Wall time / throughput",
            f"{run.wall_s:,.2f} s / {_ms(s['throughput_calls_per_s'])} calls per s",
        ),
        "",
        "## By category",
        "",
        "| Category | What it proves | Runs | Passed | Rate |",
        "|---|---|---|---|---|",
    ]
    meaning = {
        "clean": "Scripted behavior as designed",
        "injection": "Attacks in caller speech cause no unauthorized action or disclosure",
        "benign": "Same outcome when only the surface form of speech changes",
        "stress": "Harder, realistic recognition errors (reported, not gated)",
        "corrupting": "A garbled identifier never verifies the caller or unlocks their data",
    }
    for cat, c in s["categories"].items():
        lines.append(_row(cat, meaning.get(cat, ""), c["runs"], c["passed"], _fmt(c["pass_rate"])))
    lines.append("")

    if s["profiles"]:
        lines += [
            "## ASR-noise profiles",
            "",
            "| Profile | Class | Example | Runs | Passed | Rate |",
            "|---|---|---|---|---|---|",
        ]
        for name, p in s["profiles"].items():
            desc = PROFILES[name].description if name in PROFILES else ""
            lines.append(
                _row(
                    f"`{name}`",
                    p["category"],
                    _esc(desc),
                    p["runs"],
                    p["passed"],
                    _fmt(p["pass_rate"]),
                )
            )
        lines.append("")

    server = run.server_latency
    if server:
        lines += [
            "## Server-side latency (from the target's Prometheus histograms)",
            "",
            "Percentiles are estimated from histogram buckets.",
            "",
            "| Series | Count | Mean (ms) | p95 est. (ms) |",
            "|---|---|---|---|",
        ]

        def p95(t: dict[str, Any]) -> str:
            return ("≤ " if t.get("p95_is_upper_bound") else "") + _ms(t["p95_ms_est"])

        if server.get("turn"):
            t = server["turn"]
            lines.append(f"| agent turn | {t['count']} | {_ms(t['mean_ms'])} | {p95(t)} |")
        for tool, t in (server.get("tools") or {}).items():
            lines.append(f"| tool `{tool}` | {t['count']} | {_ms(t['mean_ms'])} | {p95(t)} |")
        lines.append("")

    injections = [r for r in run.results if r.category == "injection" and r.repeat == 0]
    if injections:
        lines += [
            "## Prompt-injection scenarios",
            "",
            "| Attack | Result | Tools refused | Violations | Disclosures |",
            "|---|---|---|---|---|",
        ]
        for r in injections:
            lines.append(
                f"| `{r.id}` | {'PASS' if r.passed else 'FAIL'} | {r.tool_refusals} | "
                f"{len(r.violations)} | {len(r.disclosures)} |"
            )
        lines.append("")

    clean = [r for r in run.results if r.category == "clean" and r.repeat == 0]
    if clean:
        lines += [
            "## Clean scenarios",
            "",
            "| Scenario | Result | Turns | Final status | Tasks | Turns to complete |",
            "|---|---|---|---|---|---|",
        ]
        for r in clean:
            lines.append(
                _row(
                    f"`{r.id}`",
                    "PASS" if r.passed else "FAIL",
                    len(r.turns),
                    r.final_status or "–",
                    ", ".join(r.completed_tasks) or "–",
                    _fmt(r.turns_to_complete),
                )
            )
        lines.append("")

    failed = [r for r in run.results if not r.passed]
    lines += [f"## Failures ({len(failed)})", ""]
    if not failed:
        lines.append("None.")
    for r in failed[:max_failures]:
        lines.append(f"### `{r.id}`" + (f" (repeat {r.repeat})" if run.repeats > 1 else ""))
        lines.append("")
        for f in r.failures[:6]:
            lines.append(f"- {_esc(f)}")
        if r.profile:
            lines.append(
                "- caller said: " + " → ".join(f"`{_esc(t.sent) or '(silence)'}`" for t in r.turns)
            )
        lines.append("")
    if len(failed) > max_failures:
        lines.append(f"…and {len(failed) - max_failures} more in the JSON results.")
    return "\n".join(lines).rstrip() + "\n"
