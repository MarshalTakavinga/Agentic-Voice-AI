"""``vae`` command line: validate, run, report, compare, load, profiles."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from vae import __version__, metrics, report
from vae import compare as cmp_mod
from vae.load import run_load
from vae.noise import PROFILES
from vae.runner import RunResult, expand, run_suite
from vae.scenario import Suite, load_suite
from vae.targets.http import HttpTarget


def _load_app(spec: str, app_path: list[str]) -> Any:
    """``module:attr`` or ``module:factory()``, imported with ``app_path`` on sys.path."""
    for p in reversed(app_path):
        resolved = str(Path(p).resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
    module_name, _, attr = spec.partition(":")
    call = attr.endswith("()")
    obj = getattr(importlib.import_module(module_name), attr.removesuffix("()") or "app")
    return obj() if call else obj


def _targets(args: argparse.Namespace, suite: Suite) -> list[HttpTarget]:
    key = os.environ.get(args.api_key_env or suite.target.api_key_env, "")
    timeout = suite.target.timeout_s
    if args.app:
        return [
            HttpTarget(
                app=_load_app(args.app, args.app_path),
                api_key=key,
                timeout_s=timeout,
                name=f"in-process {args.app}",
            )
        ]
    urls = [u.strip() for u in (args.base_url or suite.target.base_url).split(",") if u.strip()]
    return [HttpTarget(base_url=u, api_key=key, timeout_s=timeout) for u in urls]


def _finish(run: RunResult, suite: Suite, args: argparse.Namespace, gate: bool) -> int:
    run.summary = metrics.summarize(run)
    if gate:
        run.gates = metrics.evaluate_gates(run.summary, suite.gates)
    text = report.render(run)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(run.model_dump_json(indent=1) + "\n", encoding="utf-8")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file and args.step_summary:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    s = run.summary
    print(
        f"{run.suite}: {s['passed']}/{s['runs']} calls passed · pass rate {s['pass_rate']} · "
        f"benign {s['benign_robustness']} · corrupting safety {s['corrupting_safety']} · "
        f"unauthorized tool calls {s['unauthorized_tool_calls']} · p95 {s['latency']['p95_ms']} ms"
    )
    if gate and not metrics.gates_passed(run.gates):
        for g in run.gates:
            if g["result"] == "fail":
                print(
                    f"GATE FAILED: {g['gate']}: {g['actual']} (needs {g['threshold']})",
                    file=sys.stderr,
                )
        return 1
    return 0


async def _cmd_run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    if args.p95_budget_ms is not None:
        suite = suite.model_copy(
            update={"gates": suite.gates.model_copy(update={"max_p95_turn_ms": args.p95_budget_ms})}
        )
    profiles = None if args.profiles is None else [p for p in args.profiles.split(",") if p]
    target = _targets(args, suite)[0]
    factory = None
    if args.isolate:
        if not (args.app and args.app.endswith("()")):
            print(
                "--isolate needs an app factory, e.g. --app app.main:create_app()", file=sys.stderr
            )
            return 2
        key = os.environ.get(args.api_key_env or suite.target.api_key_env, "")

        def factory() -> HttpTarget:
            return HttpTarget(
                app=_load_app(args.app, args.app_path),
                api_key=key,
                timeout_s=suite.target.timeout_s,
                name=target.name,
            )

    try:
        run = await run_suite(
            suite,
            target,
            profiles=profiles,
            seed=args.seed,
            concurrency=args.concurrency,
            repeats=args.repeats,
            only=args.only,
            target_factory=factory,
        )
    finally:
        await target.aclose()
    return _finish(run, suite, args, gate=args.gate)


async def _cmd_load(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    targets = _targets(args, suite)
    try:
        run = await run_load(suite, targets, calls=args.calls, concurrency=args.concurrency)
    finally:
        for t in targets:
            await t.aclose()
    code = _finish(run, suite, args, gate=False)
    s = run.summary
    if args.gate and (s["passed"] < s["runs"] or s["errors"]):
        print(
            f"LOAD GATE FAILED: {s['runs'] - s['passed']} incorrect calls, {s['errors']} errors",
            file=sys.stderr,
        )
        return 1
    return code


def _cmd_validate(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    variants = expand(suite)[len(suite.scenarios) :]
    by_cat: dict[str, int] = {}
    for s in [*suite.scenarios, *variants]:
        by_cat[s.category] = by_cat.get(s.category, 0) + 1
    print(
        f"{suite.name} ({suite.fingerprint}): {len(suite.scenarios)} scenarios, "
        f"{len(variants)} noise variants"
    )
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat:11} {n}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    run = RunResult.model_validate_json(Path(args.results).read_text(encoding="utf-8"))
    text = report.render(run)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    cand = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    result = cmp_mod.compare(
        base,
        cand,
        rate_tolerance=args.rate_tolerance,
        p95_increase=None if args.ignore_latency else args.p95_increase,
        p95_floor_ms=args.p95_floor_ms,
    )
    text = cmp_mod.render(result, args.baseline, args.candidate)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file and args.step_summary:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if result.ok else 1


def _cmd_profiles(args: argparse.Namespace) -> int:
    for p in PROFILES.values():
        print(f"{p.name:16} {p.category:11} {p.description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="vae",
        description="Evaluate voice agents: regression, ASR-noise robustness, safety and load.",
    )
    ap.add_argument("--version", action="version", version=f"vae {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def target_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("suite", help="suite.yaml or the directory containing it")
        p.add_argument("--base-url", help="target URL(s), comma-separated (default: from suite)")
        p.add_argument("--app", help="evaluate an ASGI app in-process, e.g. app.main:app")
        p.add_argument(
            "--app-path", action="append", default=[], help="directory to put on sys.path for --app"
        )
        p.add_argument(
            "--api-key-env", help="env var holding the target's API key (default: from suite)"
        )
        p.add_argument("--concurrency", type=int, default=8)
        p.add_argument("--out", help="write JSON results here")
        p.add_argument("--report", help="write the Markdown report here")
        p.add_argument(
            "--step-summary", action="store_true", help="append the report to $GITHUB_STEP_SUMMARY"
        )
        p.add_argument("--gate", action="store_true", help="exit 1 if a gate fails")

    p = sub.add_parser("run", help="run a suite (scenarios + noise variants) against a target")
    target_args(p)
    p.add_argument(
        "--profiles", help="comma-separated noise profiles; '' for none (default: from suite)"
    )
    p.add_argument("--seed", type=int)
    p.add_argument(
        "--repeats", type=int, default=1, help="run everything N times to detect flakiness"
    )
    p.add_argument("--only", action="append", help="scenario id (or base id) to run; repeatable")
    p.add_argument("--p95-budget-ms", type=float, help="override the suite's p95 latency gate")
    p.add_argument(
        "--isolate",
        action="store_true",
        help="fresh in-process agent per call (needs --app module:factory())",
    )
    p.set_defaults(func=lambda a: asyncio.run(_cmd_run(a)))

    p = sub.add_parser("load", help="many concurrent calls, each checked for correctness")
    target_args(p)
    p.add_argument("--calls", type=int, default=200)
    p.set_defaults(func=lambda a: asyncio.run(_cmd_load(a)))

    p = sub.add_parser("validate", help="parse a suite and count scenarios and variants")
    p.add_argument("suite")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("report", help="render a Markdown report from JSON results")
    p.add_argument("results")
    p.add_argument("--out")
    p.set_defaults(func=_cmd_report)

    p = sub.add_parser("compare", help="fail if a candidate run regressed against a baseline")
    p.add_argument("baseline")
    p.add_argument("candidate")
    p.add_argument("--rate-tolerance", type=float, default=0.0)
    p.add_argument("--p95-increase", type=float, default=0.5)
    p.add_argument("--p95-floor-ms", type=float, default=5.0)
    p.add_argument(
        "--ignore-latency",
        action="store_true",
        help="skip the latency comparison (baseline from another machine)",
    )
    p.add_argument("--out")
    p.add_argument("--step-summary", action="store_true")
    p.set_defaults(func=_cmd_compare)

    p = sub.add_parser("profiles", help="list ASR-noise profiles")
    p.set_defaults(func=_cmd_profiles)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
