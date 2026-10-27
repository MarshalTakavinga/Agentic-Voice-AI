# Security

This is test tooling. It handles an agent's API key and the agent's replies, and it is often run in CI with access to staging systems, so its own handling matters.

## Controls

| Concern | Control |
|---|---|
| Agent API keys | Read from an environment variable named by the suite (`target.api_key_env`); never accepted as a command-line value, never written to results or reports |
| CI inputs | The GitHub Action passes every input to the shell as an environment variable, never interpolated into the script, so crafted inputs cannot inject commands |
| Test data | Suites use synthetic accounts only. Results store agent replies (truncated to 300 characters) because they are synthetic; do not point a suite at production data |
| Untrusted suites | Suites are parsed with `yaml.safe_load` and validated by strict Pydantic models (unknown fields rejected). A suite cannot execute code |
| `--app` | Imports and runs Python from the named module. Use it only with code you trust, as you would `pytest` |
| Disclosure checks | Word-boundary matching avoids false positives; see `docs/decisions.md` §6 |
| Container | Non-root user (uid 10001), slim base, dependencies pinned in `requirements.lock`, Trivy scan in CI |
| Supply chain | Bandit SAST, pip-audit on the lock file, Dependabot (repository level) |

## Known gaps

| Gap | Impact | Plan |
|---|---|---|
| The oracle trusts the agent's audit trail | An agent that hides tool calls from `events` evades the policy checks | Cross-check against the agent's tool-call metrics or traces when available |
| Text-level noise only | Acoustic failure modes (accents, line noise, codecs) are not covered | Milestone 3: TTS → recognizer round trip |
| Results JSON contains replies | If a suite were pointed at real data, replies could hold personal data | Keep suites synthetic; a redaction pass via 05-voice-pii-guard is planned |

## Reporting

Please report vulnerabilities privately through GitHub security advisories on this repository.
