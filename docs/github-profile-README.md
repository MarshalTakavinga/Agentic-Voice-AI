<!-- Save as README.md in the public repo MarshalTakavinga/MarshalTakavinga. Replace the LinkedIn slug. -->

# Marshal Takavinga

### I build AI agents that are safe to put on a phone line — and I can debug the phone line too.

Agentic AI engineer focused on **voice, IVR and contact-center modernization**. I come from network engineering (routing, SD-WAN, firewalls, telecom operations) and cloud architecture, so I design agents the way carriers design networks: deterministic where it matters, observable everywhere, and graceful when something fails.

**Azure Solutions Architect Expert** · **AWS Professional-level certified** · **M.S. Information Systems Technology, George Washington University (in progress)**

---

## How I build

| Principle | In practice |
|---|---|
| **Guardrails in code, not prompts** | Authorization, identity binding and consent are enforced by the tool layer and proven by tests. Models propose; code decides. |
| **Honest engineering** | Every README separates what is tested live from what is simulated. Numbers come from CI-generated eval reports. |
| **Runs on your laptop** | Every project demos with `make simulate` and synthetic data. No paid account required to evaluate my work. |

## Agentic Voice Platform

| Project | What it does | Stack | Status |
|---|---|---|---|
| [**agentic-voice-ivr**](https://github.com/MarshalTakavinga/Agentic-Voice-AI/tree/main/01-agentic-voice-ivr) | Conversational IVR that verifies callers, completes multi-step requests via guarded tool calls, and warm-transfers with context | FastAPI · LangGraph · Bedrock · Twilio | ![M1](https://img.shields.io/badge/milestone-1%20shipped-brightgreen) |
| [**sip-call-doctor**](https://github.com/MarshalTakavinga/Agentic-Voice-AI/tree/main/02-sip-call-doctor) | Reads SIP/RTP captures, finds one-way audio, codec and NAT faults, explains them with cited evidence | scapy · SIP/SDP · RTP · FastAPI | ![M1](https://img.shields.io/badge/milestone-1%20shipped-brightgreen) |
| [**voice-agent-evals**](https://github.com/MarshalTakavinga/Agentic-Voice-AI/tree/main/03-voice-agent-evals) | Regression and load testing for voice agents: task completion, p95 latency, injection resistance | asyncio · k6 · DuckDB | ![planned](https://img.shields.io/badge/status-planned-lightgrey) |
| [**contact-center-copilot**](https://github.com/MarshalTakavinga/Agentic-Voice-AI/tree/main/04-contact-center-copilot) | Real-time agent assist with permission-aware cited RAG and after-call summaries | pgvector · WebSockets · Amazon Connect | ![planned](https://img.shields.io/badge/status-planned-lightgrey) |
| [**voice-pii-guard**](https://github.com/MarshalTakavinga/Agentic-Voice-AI/tree/main/05-voice-pii-guard) | Redacts PII across call audio, transcripts, logs and LLM tool payloads | Presidio · ffmpeg · FastAPI | ![planned](https://img.shields.io/badge/status-planned-lightgrey) |

➡️ All ten projects, the shared architecture and the roadmap: [**Agentic-Voice-AI**](https://github.com/MarshalTakavinga/Agentic-Voice-AI)

## Skills

**Agentic AI** — LangGraph, LangChain, tool calling, multi-step workflows, RAG, evals · **LLMs** — Amazon Bedrock, OpenAI, Claude, Ollama
**Voice & CC** — SIP, RTP, IVR design, Twilio, Amazon Connect, Amazon Lex, Genesys Cloud, Asterisk, FreeSWITCH
**Backend** — Python, FastAPI, REST, microservices, Redis, PostgreSQL/pgvector
**Cloud & ops** — AWS (Lambda, API Gateway, ECS, CDK), Azure, Docker, Kubernetes, GitHub Actions, Prometheus, OpenTelemetry
**Security** — OAuth/OIDC, NIST SP 800-53 control mapping, SAST/SCA, container hardening · **Networking** — BGP, OSPF, SD-WAN, FortiGate

## Contact

[LinkedIn](https://www.linkedin.com/in/OWNER) · mttakavinga@gmail.com
