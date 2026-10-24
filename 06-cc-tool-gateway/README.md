# cc-tool-gateway

**Contact Center Tool Gateway (MCP)** · Tier: Intermediate

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Every AI team re-implements tool access to CRM and ACD systems with inconsistent security.

## Why existing approaches fall short

Ad-hoc function calling has no central policy, audit or least-privilege scoping.

## Proposed solution

One MCP server exposing contact-center actions with OAuth scopes, customer binding, consent tokens and an audit log — the guardrail registry from 01, extracted and shared.

## Architecture

MCP Python SDK server → policy engine (deny by default) → adapters (mock, Amazon Connect queue metrics, CRM mock) → audit store.

## Stack

MCP Python SDK, FastAPI admin API, Python or OPA policies.

## Milestone 1 scope

- Six tools from 01 plus `get_queue_status` and `create_case`
- Scoped tokens per client
- Policy decision log with reasons

## Success criteria

- Policy test matrix (every tool × every scope)
- 01 and 04 both call tools through it
- Demo: an MCP client is refused, with the reason shown

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
