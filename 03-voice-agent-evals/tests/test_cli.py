from __future__ import annotations

import json

import pytest

from tests.conftest import MINI
from vae.cli import main

APP = "tests.fake_agent:create_app()"


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("VAE_TEST_KEY", "test-key")


def test_validate_and_profiles(capsys):
    assert main(["validate", str(MINI)]) == 0
    assert "4 scenarios" in capsys.readouterr().out
    assert main(["profiles"]) == 0
    assert "oh_for_zero" in capsys.readouterr().out


def test_run_writes_results_report_and_step_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    out, rep = tmp_path / "r.json", tmp_path / "r.md"
    code = main(
        [
            "run",
            str(MINI),
            "--app",
            APP,
            "--profiles",
            "",
            "--out",
            str(out),
            "--report",
            str(rep),
            "--gate",
            "--step-summary",
        ]
    )
    assert code == 0
    data = json.loads(out.read_text())
    assert data["summary"]["pass_rate"] == 1.0 and data["gates"]
    assert "# Voice agent eval report" in rep.read_text() and summary.read_text()
    assert main(["report", str(out), "--out", str(tmp_path / "again.md")]) == 0


def test_run_gate_fails_for_buggy_agent(tmp_path, capsys):
    code = main(
        [
            "run",
            str(MINI),
            "--app",
            "tests.fake_agent:skip_consent_app()",
            "--profiles",
            "",
            "--gate",
        ]
    )
    assert code == 1


def test_isolation_requires_factory(capsys):
    assert main(["run", str(MINI), "--app", "tests.fake_agent:CATALOG", "--isolate"]) == 2
    assert (
        main(
            [
                "run",
                str(MINI),
                "--app",
                APP,
                "--isolate",
                "--profiles",
                "",
                "--gate",
                "--p95-budget-ms",
                "5000",
            ]
        )
        == 0
    )


def test_compare_exit_codes(tmp_path):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    assert main(["run", str(MINI), "--app", APP, "--out", str(good)]) == 0
    main(["run", str(MINI), "--app", "tests.fake_agent:unsafe_app()", "--out", str(bad)])
    assert main(["compare", str(good), str(good)]) == 0
    assert (
        main(["compare", str(good), str(bad), "--ignore-latency", "--out", str(tmp_path / "d.md")])
        == 1
    )
    assert "Regression check: FAIL" in (tmp_path / "d.md").read_text()


def test_load_command(tmp_path):
    out = tmp_path / "load.json"
    assert (
        main(
            [
                "load",
                str(MINI),
                "--app",
                APP,
                "--calls",
                "12",
                "--concurrency",
                "4",
                "--out",
                str(out),
                "--gate",
            ]
        )
        == 0
    )
    data = json.loads(out.read_text())
    assert data["summary"]["runs"] == 12 and data["summary"]["passed"] == 12
    assert data["summary"]["throughput_calls_per_s"] > 0
