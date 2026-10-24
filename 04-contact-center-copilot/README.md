# contact-center-copilot

**AI Contact Center Copilot (with Voice RAG)** · Tier: Flagship

> **Status: planned.** This folder holds the specification and a starter skeleton. Nothing here is implemented yet; see [01](../01-agentic-voice-ivr) and [02](../02-sip-call-doctor) for the standard each project will be built to.

## Problem

Agents juggle 5–10 tools, search knowledge bases mid-call and spend minutes on after-call work; answers are inconsistent.

## Why existing approaches fall short

Native vendor assist is tied to one platform and opaque; DIY RAG lacks permissions and citations, so agents don't trust it.

## Proposed solution

Streaming transcript → intent and entity tracking → permission-aware retrieval with citations → suggested replies and next actions → schema-validated after-call summary and disposition. A spoken mode covers the Voice RAG use case.

## Architecture

Transcript stream (WebSocket; simulated first, then Amazon Connect Contact Lens / Kinesis or Genesys AudioHook) → assist agent (LangGraph) → RAG service (pgvector hybrid BM25 + vector, ACL filter before retrieval) → accessible agent-desktop UI → summary service.

## Stack

FastAPI WebSockets, PostgreSQL + pgvector, sentence-transformers or Bedrock Titan embeddings, HTMX/React UI. Alternatives: Amazon Q in Connect, Kendra.

## Milestone 1 scope

- Synthetic knowledge base (~200 articles) with document-level ACLs
- Simulated calls streamed turn by turn
- Suggestions that always carry citations
- After-call summary validated against a JSON schema

## Success criteria

- Retrieval recall@5 on a labeled question set
- 100% of suggestions carry valid citations
- Summary field accuracy vs gold labels
- axe-core accessibility checks pass on the UI

## Layout

```text
src/     implementation
tests/   unit and integration tests
data/    synthetic fixtures (never real customer data)
evals/   scenario or labeled evaluation sets
docs/    design notes, ADRs
```
