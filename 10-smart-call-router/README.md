# smart-call-router

**Intelligent Call Routing Engine** · Tier: Intermediate

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Skills-based routing ignores intent nuance, customer history and real-time SLA risk.

## Why existing approaches fall short

Static routing profiles can't weigh competing constraints.

## Proposed solution

A scoring service combining intent, customer history, agent skills and proficiency, occupancy and SLA risk returns a ranked recommendation with an explanation. A discrete-event simulator measures wait time and SLA under load.

## Architecture

FastAPI scorer → SimPy simulator → baseline comparisons (FIFO, skills-only); optional LLM for explanations only — the decision itself stays deterministic.

## Stack

Python, FastAPI, SimPy.

## Milestone 1 scope

- Scorer and simulator
- Comparison against FIFO and skills-only baselines
- Feature log per decision (no protected-attribute proxies)

## Success criteria

- Simulated service level and abandonment vs baselines, clearly labeled as simulation

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
