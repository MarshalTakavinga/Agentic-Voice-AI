# voice-pii-guard

**AI Compliance & PII Redaction Platform** · Tier: Advanced

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Recordings, transcripts, logs and LLM prompts leak card numbers, SSNs and health details; PCI DSS and privacy obligations make every leak expensive.

## Why existing approaches fall short

Regex alone misses spoken forms ("four one one one…"); vendor redaction covers recordings but not app logs or tool payloads.

## Proposed solution

Layered detection — regex, checksum validators (Luhn), spoken-number normalization, Presidio NER, optional LLM second pass — applied at every boundary: audio (by word timestamps), transcripts, logs, prompts and tool I/O.

## Architecture

Detection library → FastAPI service → middleware for FastAPI / structlog / LangChain callbacks → audio redactor (ffmpeg beep or silence by timestamp) → audit log of redaction decisions, never originals.

## Stack

Microsoft Presidio, spaCy, ffmpeg, FastAPI. Compare against Amazon Comprehend PII and Transcribe PII redaction in the docs.

## Milestone 1 scope

- Text and transcript redaction with spoken-number support
- structlog middleware (generalizes the redactors in 01 and 02)
- Labeled synthetic corpus with precision/recall per entity type

## Success criteria

- Recall and precision per entity type, recall prioritized for card numbers
- Throughput benchmark
- Adopted by 01, 02 and 04

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
