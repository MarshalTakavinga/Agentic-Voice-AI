from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.fake_agent import create_app
from vae.scenario import load_suite
from vae.targets.http import HttpTarget

HERE = Path(__file__).resolve().parent
MINI = HERE / "fixtures" / "mini"
IVR_SUITE = HERE.parent / "suites" / "ivr"
KEY = "test-key"


@pytest.fixture
def mini():
    return load_suite(MINI)


def target_for(*bugs: str, slow_ms: int = 0) -> HttpTarget:
    return HttpTarget(app=create_app(frozenset(bugs), slow_ms=slow_ms), api_key=KEY, name="fake")


def run(coro):
    return asyncio.run(coro)
