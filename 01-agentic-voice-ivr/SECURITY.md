# Security

This is a portfolio reference implementation using synthetic data. It has not undergone a
security assessment, penetration test, or authorization (ATO).

## Reporting

Open a private security advisory on the repository rather than a public issue.

## Known gaps (tracked in the roadmap)

| Gap | Risk | Planned fix |
|---|---|---|
| Single shared API key for `/v1` | No per-client identity or scopes | OAuth 2.0 client credentials (Cognito / Entra ID) with scopes |
| The account number sits in session state between the account and PIN prompts | Readable by anyone with Redis access during that window | Redis with TLS and AUTH (managed service); encrypt session values at rest |
| Lockout can be triggered by someone who knows a victim's account number | Victim is routed to a human for 15 minutes (degraded, not denied) | Step-up via ANI match or one-time passcode; alert on lockout spikes (`ivr_auth_lockouts_total`) |
| The mock enterprise adapter is per replica | Two replicas could book the same slot in the demo setup | Real systems of record enforce slot uniqueness and honour the idempotency key |
| A 4-digit PIN over voice is weak authentication | Shoulder-surfing, replay | ANI match + one-time passcode or voice biometrics as step-up |
| No rate limiting | Resource exhaustion | API Gateway / WAF throttling in the AWS deployment |
| LLM planner tested against a compromised-model simulation, not yet against live Claude at scale | A real model may phrase replies the grounding check rejects (safe but less helpful) | Run `--live` injection evals; review rejected-reply rate in traces |
| Transcripts are not stored | (By design.) A real deployment needs a retention policy | Pair with the PII-redaction project in this portfolio |
