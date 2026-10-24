# Security

This is a portfolio reference implementation using synthetic data. It has not undergone a
security assessment, penetration test, or authorization (ATO).

## Reporting

Open a private security advisory on the repository rather than a public issue.

## Known gaps (tracked in the roadmap)

| Gap | Risk | Planned fix |
|---|---|---|
| Verification attempts are limited per call, not per account | Brute force across many calls | Milestone 3: per-account lockout in Redis |
| Single shared API key for `/v1` | No per-client identity or scopes | OAuth 2.0 client credentials (Cognito / Entra ID) with scopes |
| In-memory session store | State lost on restart; single replica only | Milestone 3: Redis with TTL and encryption in transit |
| A 4-digit PIN over voice is weak authentication | Shoulder-surfing, replay | ANI match + one-time passcode or voice biometrics as step-up |
| Twilio webhooks don't yet de-duplicate retries | Repeated turn on network retry | Idempotency on (CallSid, sequence) |
| No rate limiting | Resource exhaustion | API Gateway / WAF throttling in the AWS deployment |
| LLM planner tested against a compromised-model simulation, not yet against live Claude at scale | A real model may phrase replies the grounding check rejects (safe but less helpful) | Run `--live` injection evals; review rejected-reply rate in traces |
| Planner daily budget is per process | Several replicas multiply the cap | Milestone 3: shared budget counter in Redis |
| Transcripts are not stored | (By design.) A real deployment needs a retention policy | Pair with the PII-redaction project in this portfolio |
