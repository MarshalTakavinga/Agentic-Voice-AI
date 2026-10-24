from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.adapters.mock import MockCustomerSystem
from app.config import DEFAULT_DATA_DIR, Settings
from app.main import create_app

API_KEY = "test-api-key"
FIXED_TODAY = date(2026, 10, 21)  # a Wednesday, so slot tests are deterministic


@pytest.fixture
def settings() -> Settings:
    return Settings(api_key=API_KEY, log_level="WARNING", env="test")


@pytest.fixture
def system() -> MockCustomerSystem:
    return MockCustomerSystem(DEFAULT_DATA_DIR, today=lambda: FIXED_TODAY)


@pytest.fixture
def app(settings, system):
    return create_app(settings, system)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


@pytest.fixture
def service(app):
    return app.state.service


def converse(service, *utterances: str) -> dict:
    state = service.start_call(channel="test")
    for text in utterances:
        state = service.take_turn(state["call_id"], text)
    return state
