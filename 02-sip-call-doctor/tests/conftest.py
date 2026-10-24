from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sipdoc.api.app import create_app
from sipdoc.config import Settings

CAPTURES = Path(__file__).resolve().parent.parent / "captures"
API_KEY = "test-key"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(api_key=API_KEY, log_level="WARNING", env="test")))


@pytest.fixture
def headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def capture(name: str) -> Path:
    return CAPTURES / f"{name}.pcap"
