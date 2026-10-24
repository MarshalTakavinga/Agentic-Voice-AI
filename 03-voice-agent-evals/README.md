# voice-agent-evals

**Voice AI Evaluation & Load Testing Framework** · Tier: Advanced

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Teams ship voice agents with no regression safety net. Latency, task completion and safety quietly degrade whenever a model, prompt or ASR vendor changes.

## Why existing approaches fall short

Generic LLM eval tools ignore turn latency, barge-in, DTMF, ASR errors and telephony timeouts; load-testing tools don't understand conversations.

## Proposed solution

A scenario DSL (YAML) with caller personas and ASR-noise injection; runners for the JSON API and Twilio; metrics for task completion, turns-to-complete, escalation correctness, p50/p95/p99 latency and unauthorized-tool-call rate; a calibrated LLM-as-judge for open-ended quality.

## Architecture

Scenario store → async runner → target adapters (01's `/v1/calls`, Twilio) → results in DuckDB → Markdown/HTML report → CI gate. Load tests via Locust or k6 driving the same scenarios.

## Stack

Python asyncio, httpx, Locust/k6, DuckDB, Jinja2. Integrates with (rather than replaces) promptfoo / DeepEval.

## Milestone 1 scope

- Port 01's 14 scenarios to YAML and add ASR-noise variants (homophones, dropped digits)
- Latency percentiles per turn and per tool
- Prompt-injection suite: 0 unauthorized tool calls as a hard CI gate
- Markdown report + GitHub Action

## Success criteria

- Reproducible reports in CI
- Judge–human agreement (Cohen's kappa) published with the judge
- Used as a gate by 01, 02 and 04

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
