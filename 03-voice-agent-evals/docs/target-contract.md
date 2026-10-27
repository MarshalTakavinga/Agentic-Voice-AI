# Target contract

Any voice agent can be evaluated by implementing four HTTP endpoints. `01-agentic-voice-ivr` implements them as its `/v1` API; the planned orchestrator (07) will implement the same contract so this suite runs unchanged against it.

All requests carry `X-API-Key` when the agent requires one.

| Endpoint | Purpose | Response |
|---|---|---|
| `GET /v1/tools` | Tool catalog with policy flags | `[{"name", "requires_auth", "side_effect", ...}]` |
| `POST /v1/calls` | Start a call (body `{"channel": "api"}`) | Turn view, HTTP 201 |
| `POST /v1/calls/{id}/turns` | One caller turn (body `{"text": "..."}`: ASR text, DTMF digits, or `""` for silence) | Turn view; **409** once the call has ended |
| `GET /v1/calls/{id}` | Current view plus the tool audit trail | Turn view with `events` |
| `GET /metrics` *(optional)* | Prometheus text; enables server-side latency per tool | |

## Turn view

| Field | Type | Used for |
|---|---|---|
| `call_id` | string | |
| `status` | `in_progress` · `completed` · `escalated` | final checks, escalation metrics |
| `reply` | string | `contains` / `not_contains`, disclosures |
| `turn` | int | caller turns so far |
| `expecting` | string or null | slot being collected (turn checks) |
| `authenticated` | bool | final checks, `auth_required` rule |
| `awaiting_confirmation` | bool | `consent_required` rule |
| `completed_tasks` | list of strings | task completion, turns to complete |
| `handoff` | object or null (`reason`, `queue`) | escalation correctness |
| `intent`, `nlu_source` | optional | reported only |

Unknown fields are ignored.

## Audit events

`events` is the ordered list of every tool call in the call, **including refused ones**:

```json
{"turn": 3, "tool": "verify_caller", "ok": true, "error": null}
```

`turn` is the caller turn during which the tool ran (1-based). The policy oracle judges successful calls against the catalog flags and the view *before* that turn. An agent that hides tool calls from this list defeats the audit; one that runs tools missing from the catalog is reported (`uncatalogued_tool`) unless the suite maps them with `target.tool_aliases`.

## Isolation

For in-process evaluation, expose an app factory (e.g. `app.main:create_app()`) and run with `--isolate`: each scenario gets a fresh agent, so state such as lockouts and bookings cannot leak between scenarios.
