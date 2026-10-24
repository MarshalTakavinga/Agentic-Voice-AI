# voice-agent-orchestrator

**Multi-Agent Voice Workflow Orchestrator** · Tier: Advanced

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Single voice agents become unmaintainable as domains grow; one prompt ends up carrying every policy.

## Why existing approaches fall short

Monolithic agents conflate billing, scheduling and support rules and give every capability every tool.

## Proposed solution

A supervisor graph routes to specialist subgraphs (authentication, billing, scheduling, tech support, escalation). Each specialist gets only its own tools; verified identity is propagated as a signed claim.

## Architecture

LangGraph supervisor + subgraphs, tools via 06, Redis session state, the same `/v1/calls` API as 01 so 03's evals run unchanged.

## Stack

LangGraph, FastAPI, Redis. Alternatives: Bedrock multi-agent collaboration, CrewAI.

## Milestone 1 scope

- Supervisor + three specialists
- 01's scenario suite plus cross-domain scenarios
- Trace view of delegations

## Success criteria

- Matches or beats 01's pass rate on the shared suite at a stated cost per call
- Zero cross-specialist tool use in tests

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
