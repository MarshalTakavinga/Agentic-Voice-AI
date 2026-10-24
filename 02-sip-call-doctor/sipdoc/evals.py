"""Detection evaluation against labeled captures: per-signature precision and recall.

The bundled captures are synthetic and were written alongside the analyzers, so a perfect score
shows the analyzers behave as designed. It is not a measure of accuracy on real traffic; add
lab or production captures (with labels) to captures/ for that.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sipdoc.analyzers import SIGNATURES
from sipdoc.engine import analyze_capture

CAPTURES = Path(__file__).resolve().parent.parent / "captures"


def evaluate(captures_dir: Path = CAPTURES) -> dict[str, Any]:
    labels = json.loads((captures_dir / "labels.json").read_text())
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    rows, root_hits = [], 0
    for name, label in labels.items():
        report, _ = analyze_capture(captures_dir / f"{name}.pcap")
        found = {f.signature for d in report.calls for f in d.findings}
        root = report.calls[0].root_cause if report.calls else None
        expected = set(label["signatures"])
        for s in found & expected:
            tp[s] += 1
        for s in found - expected:
            fp[s] += 1
        for s in expected - found:
            fn[s] += 1
        root_ok = root == label["root_cause"]
        root_hits += root_ok
        rows.append(
            {
                "capture": name,
                "expected": sorted(expected),
                "found": sorted(found),
                "root_cause": root,
                "root_cause_ok": root_ok,
                "exact": found == expected and root_ok,
            }
        )
    per_sig = {}
    for s in SIGNATURES:
        p_den, r_den = tp[s] + fp[s], tp[s] + fn[s]
        per_sig[s] = {
            "tp": tp[s],
            "fp": fp[s],
            "fn": fn[s],
            "precision": round(tp[s] / p_den, 3) if p_den else None,
            "recall": round(tp[s] / r_den, 3) if r_den else None,
        }
    return {
        "captures": len(rows),
        "exact_matches": sum(r["exact"] for r in rows),
        "root_cause_accuracy": round(root_hits / len(rows), 3) if rows else 0.0,
        "false_positives": sum(fp.values()),
        "false_negatives": sum(fn.values()),
        "signatures": per_sig,
        "rows": rows,
    }
