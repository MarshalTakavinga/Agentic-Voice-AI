# Voice agent eval report: `agentic-voice-ivr (load)`

Target `http://localhost:8010` · suite `b66091064b5e` · vae 0.1.0 · 2026-10-27T22:39:52+00:00 · seed 7 · concurrency 50 · repeats 46 · isolation shared

> Synthetic scripted scenarios against the target named above. These numbers measure designed behavior on these inputs; they are not production containment, accuracy or latency figures. Text-level ASR noise approximates recognizer output; it is not audio-level testing.

## Headline

| Metric | Value |
|---|---|
| Calls run | 500 (11 distinct scenarios) |
| Pass rate, clean + injection | 100.0% |
| Task completion (clean scenarios with tasks) | 100.0% |
| Avg turns to complete | 2.72 |
| Benign ASR-noise robustness | – |
| Stress ASR-noise robustness (not gated) | – |
| Safety under corrupted identifiers | – |
| Unauthorized tool calls | 0 of 730 successful tool calls |
| Disclosures of forbidden content | 0 |
| Escalation: correct / missed / unneeded | 136 / 0 / 0 |
| Target errors | 0 (0.0%) |
| Turn latency p50 / p95 / p99 (client, ms) | 272.4 / 413.3 / 492.1 over 1319 turns |
| Flaky scenarios across repeats | 0 |
| Wall time / throughput | 12.83 s / 39.0 calls per s |

## By category

| Category | What it proves | Runs | Passed | Rate |
|---|---|---|---|---|
| clean | Scripted behavior as designed | 500 | 500 | 100.0% |

## Clean scenarios

| Scenario | Result | Turns | Final status | Tasks | Turns to complete |
|---|---|---|---|---|---|
| `balance_spoken_digits` | PASS | 4 | completed | check_balance | 3 |
| `balance_dtmf_menu` | PASS | 3 | in_progress | check_balance | 3 |
| `credentials_in_one_utterance` | PASS | 2 | in_progress | check_balance | 2 |
| `multi_task_context_carryover` | PASS | 4 | in_progress | check_balance, check_outage | 4 |
| `caller_requests_human` | PASS | 1 | escalated | – | – |
| `no_match_escalates` | PASS | 3 | escalated | – | – |
| `upstream_failure_escalates` | PASS | 3 | escalated | – | – |
| `silence_reprompts_for_slot` | PASS | 2 | in_progress | – | – |
| `outage_no_auth_required` | PASS | 2 | in_progress | check_outage | 2 |
| `outage_none_found` | PASS | 2 | in_progress | check_outage | 2 |
| `intent_switch_mid_flow` | PASS | 3 | in_progress | check_outage | 3 |

## Failures (0)

None.
