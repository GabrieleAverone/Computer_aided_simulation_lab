import numpy as np
from warmup import MultiWarmupDetector, WarmupDetector


def run(series, **kw):
    d = WarmupDetector(max_t=len(series) // 2, **kw)
    for t, v in enumerate(series):
        if d.update(t, v):
            break
    return d


def test_transient_then_stationary():
    rng = np.random.default_rng(0)
    t = np.arange(20000)
    d = run(10 * (1 - np.exp(-t / 1000)) + rng.normal(0, 0.3, t.size))
    assert d.stationary is True and d.warmup_end > 1000


def test_stationary_detects_early():
    d = run(np.random.default_rng(1).normal(5, 0.3, 20000))
    assert d.stationary is True and d.warmup_end <= 500


def test_linear_trend_times_out():
    d = run(0.01 * np.arange(20000) + np.random.default_rng(2).normal(0, 0.3, 20000))
    assert d.stationary is False and d.warmup_end is None


def test_multi_waits_for_all():
    m = MultiWarmupDetector([WarmupDetector(max_t=9999), WarmupDetector(max_t=9999)])
    rng = np.random.default_rng(3)
    for t in range(8000):
        m.update(t, (5 + rng.normal(0, .1), 5 * (1 - np.exp(-t / 800))))
    assert m.stationary is True and m.warmup_end == max(d.warmup_end for d in m.detectors)
