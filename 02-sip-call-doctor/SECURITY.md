# Security

Portfolio reference implementation using synthetic captures. Not security-assessed.

## Reporting

Open a private security advisory on the repository rather than a public issue.

## Data handling

| Data | Handling |
|---|---|
| Uploaded capture | Written to a private temp directory, parsed, deleted before the response returns |
| RTP payload (audio) | Never read past the 12-byte RTP header |
| Phone numbers / SIP users | Reports show the last four digits only; logs redact SIP user parts and digit runs |
| Derived reports | Bounded in-memory store (default 100, oldest evicted); lost on restart |

## Known gaps

| Gap | Risk | Planned fix |
|---|---|---|
| Packet dissection of untrusted files runs in the API process | A parser bug could be exploited by a crafted capture | Run analysis in a separate, resource-limited worker (seccomp/gVisor, or Lambda) with a timeout |
| Single shared API key | No per-user identity or audit | OIDC with scoped tokens |
| No per-client rate limiting | Resource exhaustion via large uploads | Gateway throttling; per-key quotas |
| Report store is unauthenticated per-object | Anyone with the key can read any analysis ID | Owner-scoped analyses once OIDC lands |
| SIP over TCP/TLS and SRTP are not parsed | Encrypted or stream-transport calls produce no findings | Milestone 3 |
