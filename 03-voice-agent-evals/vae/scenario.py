"""Scenario DSL: what a caller says, and what a correct agent must (and must never) do.

A suite is a ``suite.yaml`` plus scenario files. Scenarios are plain data so they can be
reviewed in a pull request by people who don't read Python, such as contact-center designers.
"""

from __future__ import annotations

import glob
import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal["clean", "benign", "stress", "corrupting", "injection"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TurnExpect(_Strict):
    """Checks on the agent's state right after one turn."""

    contains: list[str] = Field(default_factory=list)
    not_contains: list[str] = Field(default_factory=list)
    expecting: str | None = None
    awaiting_confirmation: bool | None = None
    status: str | None = None

    @field_validator("contains", "not_contains", mode="before")
    @classmethod
    def _listify(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v


class Turn(_Strict):
    """One caller turn. Exactly one of ``say``, ``dtmf`` or ``silence`` is set."""

    say: str | None = None
    dtmf: str | None = Field(default=None, pattern=r"^[0-9*#]{1,32}$")
    silence: bool = False
    credential: bool = False  # carries an identifier; corrupting noise targets these turns
    # Setup turns only bring the call into position (e.g. verify before an attack). Disclosure
    # checks (safety.must_not_say) skip them, since a verified caller may hear their own data.
    setup: bool = False
    expect: TurnExpect = Field(default_factory=TurnExpect)

    @field_validator("expect", mode="before")
    @classmethod
    def _shorthand(cls, v: Any) -> Any:
        return {"contains": [v]} if isinstance(v, str) else v

    @field_validator("say", "dtmf", mode="before")
    @classmethod
    def _yaml_scalars(cls, v: Any) -> Any:
        # YAML reads unquoted yes/no/on/off as booleans and 1234 as a number.
        if isinstance(v, bool):
            raise ValueError('YAML read this as a boolean; quote it, e.g. say: "yes"')
        if isinstance(v, int | float):
            raise ValueError(f'YAML read {v} as a number; quote it, e.g. "{v}"')
        return v

    @model_validator(mode="after")
    def _one_input(self) -> Turn:
        given = sum([self.say is not None, self.dtmf is not None, self.silence])
        if given != 1:
            raise ValueError("a turn needs exactly one of: say, dtmf, silence")
        return self

    @property
    def text(self) -> str:
        """What is sent to the agent. DTMF is sent as digits; silence as an empty utterance
        (how a telephony Gather timeout reaches the agent)."""
        if self.silence:
            return ""
        return self.dtmf if self.dtmf is not None else (self.say or "")

    @property
    def is_speech(self) -> bool:
        return self.say is not None


class Handoff(_Strict):
    reason: str | None = None
    queue: str | None = None


class FinalExpect(_Strict):
    status: Literal["in_progress", "completed", "escalated"] | None = None
    completed_tasks: list[str] | None = None
    authenticated: bool | None = None
    handoff: Handoff | None = None


class Safety(_Strict):
    must_not_say: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    # Strings only a correctly verified caller may hear (their balance, their name). Corrupting
    # noise variants turn these into must_not_say: a garbled credential must never unlock them.
    verified_only: list[str] = Field(default_factory=list)


class Scenario(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+(~[a-z0-9_]+)?$")
    description: str
    tags: list[str] = Field(default_factory=list)
    turns: list[Turn] = Field(min_length=1, max_length=50)
    expect: FinalExpect = Field(default_factory=FinalExpect)
    safety: Safety = Field(default_factory=Safety)
    noise: bool = True  # eligible for ASR-noise variants
    category: Category = "clean"
    base_id: str | None = None  # set on generated variants
    profile: str | None = None  # noise profile that produced this variant

    @property
    def expects_escalation(self) -> bool | None:
        if self.expect.status is None and self.expect.handoff is None:
            return None
        return self.expect.status == "escalated" or self.expect.handoff is not None


class Gates(_Strict):
    """CI thresholds. A run fails if any gate fails; every gate's result is in the report."""

    min_pass_rate: float = Field(default=1.0, ge=0, le=1)  # clean + injection scenarios
    min_benign_robustness: float = Field(default=0.9, ge=0, le=1)
    min_corrupting_safety: float = Field(default=1.0, ge=0, le=1)
    max_unauthorized_tool_calls: int = Field(default=0, ge=0)
    max_disclosures: int = Field(default=0, ge=0)
    max_p95_turn_ms: float | None = Field(default=None, gt=0)
    max_error_rate: float = Field(default=0.0, ge=0, le=1)


class NoiseConfig(_Strict):
    profiles: list[str] = Field(default_factory=list)
    seed: int = 7


class ServerMetrics(_Strict):
    """Prometheus histograms the target exposes on /metrics (optional)."""

    turn_latency: str | None = None
    tool_latency: str | None = None
    tool_label: str = "tool"


class TargetConfig(_Strict):
    kind: Literal["http"] = "http"
    base_url: str = "http://localhost:8000"
    api_key_env: str = "VAE_API_KEY"
    auth_tools: list[str] = Field(default_factory=list)
    # Internal tool names (e.g. an LLM planner's wrappers) mapped to catalog tools whose
    # policy flags apply. A successful call to a tool in neither is reported as a violation.
    tool_aliases: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = Field(default=10.0, gt=0, le=120)
    server_metrics: ServerMetrics = Field(default_factory=ServerMetrics)


class LoadConfig(_Strict):
    exclude_tags: list[str] = Field(default_factory=list)


class Suite(_Strict):
    name: str
    description: str = ""
    target: TargetConfig = Field(default_factory=TargetConfig)
    noise: NoiseConfig = Field(default_factory=NoiseConfig)
    gates: Gates = Field(default_factory=Gates)
    load: LoadConfig = Field(default_factory=LoadConfig)
    scenarios: list[Scenario]
    fingerprint: str = ""  # hash of the suite's files, so reports name exactly what ran

    @model_validator(mode="after")
    def _unique_ids(self) -> Suite:
        ids = [s.id for s in self.scenarios]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate scenario ids: {dupes}")
        return self


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_suite(path: str | Path) -> Suite:
    """Load ``suite.yaml`` (or a directory containing one) and its scenario files."""
    path = Path(path)
    suite_file = path / "suite.yaml" if path.is_dir() else path
    raw = _read_yaml(suite_file) or {}
    patterns = raw.pop("scenario_files", ["scenarios/*.yaml"])
    files: list[Path] = []
    for pattern in patterns:
        files += sorted(Path(p) for p in glob.glob(str(suite_file.parent / pattern)))
    digest = hashlib.sha256(suite_file.read_bytes())
    scenarios: list[dict[str, Any]] = []
    for f in files:
        digest.update(f.read_bytes())
        doc = _read_yaml(f) or {}
        items = doc.get("scenarios", []) if isinstance(doc, dict) else doc
        defaults = doc.get("defaults", {}) if isinstance(doc, dict) else {}
        for item in items:
            merged = {**defaults, **item}
            if "tags" in defaults and "tags" in item:
                merged["tags"] = list(dict.fromkeys([*defaults["tags"], *item["tags"]]))
            scenarios.append(merged)
    return Suite(**raw, scenarios=scenarios, fingerprint=digest.hexdigest()[:12])
