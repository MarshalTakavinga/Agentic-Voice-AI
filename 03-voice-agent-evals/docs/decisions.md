# Decisions

Short records of the choices that shape this framework, with what was rejected and why.

## 1. Black-box evaluation through the turn API

**Decision.** The framework talks to agents only through their public turn API (HTTP, or the same API in-process over ASGI).

**Rejected.** Importing the agent and calling its internals, as 01's own eval harness does.

**Why.** What callers and telephony channels reach is the API; testing there catches serialization, status-code and state-handling bugs that unit tests skip, and the same suite works for any agent that implements the contract. The cost: some worst cases need internals. Replaying attacks through a *compromised model* requires replacing the model, so 01 keeps that test and this framework does not duplicate it.

## 2. An independent policy oracle

**Decision.** Authorization and consent are re-checked from the agent's published catalog and audit trail, with no code shared with the agent's guardrails.

**Why.** If the test used the agent's own policy code, a bug in that code would pass its own test. The oracle needs only facts the agent must publish anyway. Successful calls to tools the catalog does not list are themselves a finding, because they cannot be audited.

## 3. Three classes of ASR noise

**Decision.** Benign variants must pass the full scenario; stress variants are reported; corrupting variants must be *safe* (no verification, no `verified_only` content).

**Rejected.** A single "noisy" pass rate.

**Why.** "The agent understood 'oh' as zero" and "the agent refused to verify a garbled account number" are both correct behavior but opposite outcomes. Mixing them in one rate makes the number meaningless; separating them makes a corrupting failure a security finding instead of noise.

## 4. Isolation is explicit

**Decision.** `--isolate` runs each scenario on a fresh in-process agent; load runs exclude scenarios tagged `stateful`.

**Why.** The first run against the IVR showed scenario outcomes depending on scheduling order: deliberate wrong PINs tripped a per-account lockout that other scenarios then hit, and bookings consumed each other's slots. Those features were working correctly. Results that depend on order are not regression results, so isolation is the default in CI, and shared-state behavior is covered separately under load.

## 5. Gates and a baseline, latency compared only on like hardware

**Decision.** Absolute gates in `suite.yaml`, plus `vae compare` against a committed baseline. CI compares rates and outcomes but not latency (`--ignore-latency`), because the baseline was measured on a different machine; latency is gated absolutely instead.

**Why.** A gate at 90% does not notice a fall from 100% to 92%; the comparison does. Comparing latency across machines would fail or pass for reasons unrelated to the change.

## 6. Disclosures match whole words

**Decision.** `must_not_say` strings match at word boundaries when they start or end with a word character.

**Why.** The first draft flagged "Ava" inside "available" and "50" inside "1500". A safety check with false positives gets ignored; one with false negatives is worse, so the boundary only applies at word characters ("$42.50" still matches after a dollar sign).
