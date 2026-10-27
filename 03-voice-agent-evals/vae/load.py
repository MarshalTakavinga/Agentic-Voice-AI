"""Load mode: the same conversations, many at once, checked for correctness under concurrency.

Generic HTTP load tools measure requests per second. A voice agent can stay fast under load and
still be wrong (a turn lost, two replicas disagreeing about a call). Every call here is a full
scenario with its expectations and policy checks, so the report says how many calls were still
*correct*, not only how quickly they were answered.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from vae.policy import PolicyOracle
from vae.runner import RunResult, ScenarioResult, run_scenario
from vae.scenario import Suite
from vae.targets.base import Target


async def run_load(
    suite: Suite,
    targets: list[Target],
    *,
    calls: int = 200,
    concurrency: int = 25,
    categories: tuple[str, ...] = ("clean",),
) -> RunResult:
    """Run ``calls`` scenario executions, cycling through the suite's scenarios and spreading
    calls round-robin across ``targets`` (each call stays on one target)."""
    excluded = set(suite.load.exclude_tags)
    pool = [s for s in suite.scenarios if s.category in categories and not excluded & set(s.tags)]
    if not pool:
        raise ValueError(f"no scenarios in categories {categories}")
    catalog = await targets[0].catalog()
    oracle = PolicyOracle(catalog, suite.target.auth_tools, suite.target.tool_aliases)
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(i: int) -> ScenarioResult:
        async with sem:
            return await run_scenario(
                targets[i % len(targets)], oracle, pool[i % len(pool)], i // len(pool)
            )

    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    results = await asyncio.gather(*(one(i) for i in range(calls)))
    wall = time.perf_counter() - t0
    return RunResult(
        suite=f"{suite.name} (load)",
        fingerprint=suite.fingerprint,
        target=", ".join(t.name for t in targets),
        started_at=started_at,
        seed=suite.noise.seed,
        profiles=[],
        concurrency=concurrency,
        repeats=-(-calls // len(pool)),
        catalog=sorted(t.name for t in catalog),
        results=list(results),
        wall_s=round(wall, 3),
    )
