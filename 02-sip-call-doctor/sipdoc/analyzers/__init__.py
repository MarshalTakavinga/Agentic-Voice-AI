from sipdoc.analyzers.rules import ANALYZERS, ROOT_CAUSE_ORDER, SIGNATURES
from sipdoc.models import SEVERITY_RANK, CallFlow, Finding

__all__ = ["SIGNATURES", "analyze_call", "pick_root_cause"]


def analyze_call(call: CallFlow) -> list[Finding]:
    findings = [f for analyzer in ANALYZERS for f in analyzer(call)]
    findings.sort(key=lambda f: (ROOT_CAUSE_ORDER.index(f.signature), SEVERITY_RANK[f.severity]))
    for i, f in enumerate(findings, start=1):
        f.id = f"F{i}"
    return findings


def pick_root_cause(findings: list[Finding]) -> Finding | None:
    return findings[0] if findings else None  # already ordered by precedence
