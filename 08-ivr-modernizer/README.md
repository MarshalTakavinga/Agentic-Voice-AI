# ivr-modernizer

**Legacy IVR Modernization Accelerator** · Tier: Intermediate

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Thousands of legacy DTMF flows (VoiceXML, Avaya, Cisco UCCX) block migrations to Amazon Connect and Genesys Cloud.

## Why existing approaches fall short

Manual redesign is slow and loses paths; nobody can prove the new flow covers the old one.

## Proposed solution

Parse menu trees → graph model → LLM proposes intents, sample utterances and slots → generate a LangGraph or Amazon Connect flow with DTMF fallback preserved → verify every legacy path is still reachable.

## Architecture

VoiceXML/JSON parsers (lxml) → networkx graph → generator with schema validation → exporters for Connect contact-flow JSON and Lex V2 bot definitions → coverage checker.

## Stack

Python, lxml, networkx, an LLM with JSON-schema validation, AWS CLI for import validation.

## Milestone 1 scope

- VoiceXML → graph → coverage report → conversational spec
- A synthetic 40-node bank IVR as the fixture

## Success criteria

- 100% legacy-path reachability
- Generated Connect flow imports cleanly (when validated live)

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
