# Conversation eval report

Synthetic scripted scenarios against the rules NLU and mock adapters. This measures designed behavior, not production performance.

| Scenario | Result | Turns | Final status | Tasks completed |
|---|---|---|---|---|
| `balance_spoken_digits` | PASS | 4 | completed | check_balance |
| `balance_dtmf_menu` | PASS | 3 | in_progress | check_balance |
| `credentials_in_one_utterance` | PASS | 2 | in_progress | check_balance |
| `outage_no_auth_required` | PASS | 2 | in_progress | check_outage |
| `outage_none_found` | PASS | 2 | in_progress | check_outage |
| `multi_task_context_carryover` | PASS | 4 | in_progress | check_balance, check_outage |
| `schedule_and_confirm` | PASS | 4 | in_progress | schedule_technician |
| `schedule_decline_then_choose_day` | PASS | 6 | in_progress | schedule_technician |
| `intent_switch_mid_flow` | PASS | 3 | in_progress | check_outage |
| `auth_failure_escalates` | PASS | 7 | escalated | - |
| `caller_requests_human` | PASS | 1 | escalated | - |
| `no_match_escalates` | PASS | 3 | escalated | - |
| `upstream_failure_escalates` | PASS | 3 | escalated | - |
| `silence_reprompts_for_slot` | PASS | 2 | in_progress | - |

```json
{
  "scenarios": 14,
  "passed": 14,
  "pass_rate": 1.0,
  "escalated": 4,
  "avg_turns": 3.29,
  "avg_agent_ms_per_turn": 5.0
}
```
