from __future__ import annotations

from vae import promscrape


def hist(name: str, label: str | None, value: str | None, buckets: dict, total: float) -> str:
    lab = f'{label}="{value}",' if label else ""
    lines = [f"# TYPE {name} histogram"]
    for le, c in buckets.items():
        lines.append(f'{name}_bucket{{{lab}le="{le}"}} {c}')
    count = buckets["+Inf"]
    tail = f"{{{lab[:-1]}}}" if lab else ""
    lines += [f"{name}_count{tail} {count}", f"{name}_sum{tail} {total}"]
    return "\n".join(lines) + "\n"


BEFORE = hist("lat_seconds", "tool", "a", {"0.005": 1, "0.1": 1, "1.0": 1, "+Inf": 1}, 0.001)
AFTER = hist("lat_seconds", "tool", "a", {"0.005": 1, "0.1": 11, "1.0": 21, "+Inf": 21}, 5.001)


def test_parse_and_delta():
    b = promscrape.parse_histograms(BEFORE, "lat_seconds", "tool")
    a = promscrape.parse_histograms(AFTER, "lat_seconds", "tool")
    d = promscrape.delta(b, a)["a"]
    assert d.count == 20 and round(d.total, 3) == 5.0
    assert d.buckets[0.005] == 0 and d.buckets[0.1] == 10


def test_quantile_interpolates_within_bucket():
    s = promscrape.delta(
        promscrape.parse_histograms(BEFORE, "lat_seconds", "tool"),
        promscrape.parse_histograms(AFTER, "lat_seconds", "tool"),
    )["a"]
    value, bound = promscrape.quantile(s, 0.5)
    assert bound is False and abs(value - 0.1) < 1e-9
    value, _ = promscrape.quantile(s, 0.95)
    assert 0.1 < value < 1.0


def test_quantile_in_lowest_bucket_is_an_upper_bound():
    s = promscrape.HistogramSeries(buckets={0.005: 10, 0.1: 10, float("inf"): 10}, count=10)
    assert promscrape.quantile(s, 0.95) == (0.005, True)


def test_quantile_edge_cases():
    assert promscrape.quantile(promscrape.HistogramSeries(), 0.5) == (None, False)
    s = promscrape.HistogramSeries(buckets={0.1: 0, float("inf"): 10}, count=10)
    assert promscrape.quantile(s, 0.95) == (None, False)


def test_summarize_unlabelled_and_missing():
    before = hist("turn_seconds", None, None, {"0.01": 0, "+Inf": 0}, 0)
    after = hist("turn_seconds", None, None, {"0.01": 2, "+Inf": 4}, 0.2)
    out = promscrape.summarize(before, after, "turn_seconds", None)
    assert out["all"]["count"] == 4 and out["all"]["mean_ms"] == 50.0
    assert out["all"]["p95_ms_est"] is None
    assert promscrape.summarize(None, after, "turn_seconds", None) == {}
