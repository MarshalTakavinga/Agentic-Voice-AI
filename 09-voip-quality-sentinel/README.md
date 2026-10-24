# voip-quality-sentinel

**AI Call Quality & Anomaly Detection** · Tier: Advanced

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Voice quality problems surface through customer complaints hours later.

## Why existing approaches fall short

Static thresholds alert noisily and miss gradual degradation.

## Proposed solution

Time-series anomaly detection on MOS, jitter, loss and post-dial delay by site, trunk and codec, correlated with infrastructure events; an incident agent drafts summaries linking to 02's packet-level evidence.

## Architecture

Synthetic telemetry generator → Prometheus/VictoriaMetrics → detectors (statsmodels, isolation forest) → LangGraph incident agent → Grafana.

## Stack

Python, Prometheus, Grafana, statsmodels, scikit-learn.

## Milestone 1 scope

- Three detectors on synthetic telemetry with injected faults
- Grafana dashboard with annotated incidents

## Success criteria

- Precision, recall and time-to-detect on injected faults

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
