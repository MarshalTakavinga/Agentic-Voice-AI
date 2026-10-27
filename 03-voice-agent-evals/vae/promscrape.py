"""Server-side latency from the target's Prometheus histograms.

Client-measured turn latency includes the network and serialization. The agent's own histograms
say where the time went inside it (per tool, per turn). Scraping ``/metrics`` before and after
a run and subtracting gives the distribution for exactly this run's traffic.

Percentiles from histogram buckets are estimates (linear interpolation inside a bucket, as
PromQL's ``histogram_quantile`` does), so the report labels them as such.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from prometheus_client.parser import text_string_to_metric_families


@dataclass
class HistogramSeries:
    buckets: dict[float, float] = field(default_factory=dict)  # upper bound -> cumulative count
    count: float = 0.0
    total: float = 0.0


def parse_histograms(text: str, metric: str, label: str | None) -> dict[str, HistogramSeries]:
    """Histogram series of ``metric`` keyed by ``label`` value ("" when unlabelled)."""
    out: dict[str, HistogramSeries] = defaultdict(HistogramSeries)
    for family in text_string_to_metric_families(text):
        if family.name != metric.removesuffix("_seconds") and family.name != metric:
            continue
        for s in family.samples:
            key = s.labels.get(label, "") if label else ""
            series = out[key]
            if s.name.endswith("_bucket"):
                series.buckets[float(s.labels["le"])] = s.value
            elif s.name.endswith("_count"):
                series.count = s.value
            elif s.name.endswith("_sum"):
                series.total = s.value
    return dict(out)


def delta(
    before: dict[str, HistogramSeries], after: dict[str, HistogramSeries]
) -> dict[str, HistogramSeries]:
    out = {}
    for key, a in after.items():
        b = before.get(key, HistogramSeries())
        d = HistogramSeries(
            buckets={le: v - b.buckets.get(le, 0.0) for le, v in a.buckets.items()},
            count=a.count - b.count,
            total=a.total - b.total,
        )
        if d.count > 0:
            out[key] = d
    return out


def quantile(series: HistogramSeries, q: float) -> tuple[float | None, bool]:
    """Estimated q-quantile in seconds, and whether it is only an upper bound.

    Inside the lowest bucket there is nothing to interpolate from, so the bucket's bound is
    returned and flagged ("<= 5 ms"), rather than a made-up 4.8 ms. None if the rank falls in
    the +Inf bucket."""
    if series.count <= 0:
        return None, False
    rank = q * series.count
    prev_le, prev_count = 0.0, 0.0
    for le in sorted(series.buckets):
        count = series.buckets[le]
        if count >= rank:
            if le == float("inf"):
                return None, False
            if prev_le == 0.0:  # inside the first bucket: only its bound is known
                return le, True
            span = count - prev_count
            frac = (rank - prev_count) / span if span else 0.0
            return prev_le + (le - prev_le) * frac, False
        prev_le, prev_count = le, count
    return None, False


def summarize(
    before: str | None, after: str | None, metric: str, label: str | None
) -> dict[str, dict[str, float | None]]:
    """{label value: {count, mean_ms, p95_ms_est}} for traffic between the two scrapes."""
    if not before or not after:
        return {}
    d = delta(parse_histograms(before, metric, label), parse_histograms(after, metric, label))
    out = {}
    for key, s in sorted(d.items()):
        p95, bound = quantile(s, 0.95)
        out[key or "all"] = {
            "count": int(s.count),
            "mean_ms": round(s.total / s.count * 1000, 3),
            "p95_ms_est": round(p95 * 1000, 3) if p95 is not None else None,
            "p95_is_upper_bound": bound,
        }
    return out
