"""Test del WarmupDetector (eseguibili con pytest, oppure `python test_warmup_detector.py`)."""

import pytest

from WarmupDetector import WarmupDetector, linearSlope


def feed(detector, values, var="a"):
    for t, v in enumerate(values, 1):
        detector.update(t, {var: v})


def test_window_mean_is_time_weighted():
    d = WarmupDetector(3, ("a",))
    feed(d, [1, 4, 2])                      # dt = 1 per evento (t=1,2,3): (1+4+2)/3
    assert d.windowMeans["a"] == [pytest.approx(7 / 3)]
    d.update(5, {"a": 3})                   # dt = 2
    d.update(6, {"a": 1})
    d.update(7, {"a": 1})
    assert d.windowMeans["a"][1] == pytest.approx((3 * 2 + 1 + 1) / 4)


def test_linear_slope_matches_known_values():
    assert linearSlope([1, 2, 3, 4, 5]) == (pytest.approx(1.0), pytest.approx(0.0))
    slope, se = linearSlope([1, 3, 2, 4, 3.5, 5])      # confrontato con scipy.stats.linregress
    assert slope == pytest.approx(0.6714285714)
    assert se == pytest.approx(0.1820144243)


@pytest.mark.parametrize("mode", ["mean", "slope", "both"])
def test_detects_plateau(mode):
    d = WarmupDetector(1, ("a",), t=5, eps=0.1, confirm=2, mode=mode)
    feed(d, [0, 10, 20, 30, 40, 50] + [50.0, 50.2, 49.9, 50.1, 50.0, 49.8, 50.1, 50.0])
    assert d.warmupDone and d.detectionTime is not None


@pytest.mark.parametrize("mode", ["slope", "both"])
def test_does_not_detect_steady_growth(mode):
    d = WarmupDetector(1, ("a",), t=5, eps=10.0, confirm=2, mode=mode)
    feed(d, [i * 1.0 + (0.1 if i % 2 else 0) for i in range(60)])
    assert not d.warmupDone


def test_mean_test_alone_is_fooled_by_slow_growth():
    # crescita lenta ma continua: con una tolleranza larga il solo test sulla media scatta
    d = WarmupDetector(1, ("a",), t=5, eps=0.5, confirm=2, mode="mean")
    feed(d, [100 + i for i in range(60)])
    assert d.warmupDone


def test_absolute_tolerance_overrides_relative():
    noisy = [10 + (0.3 if i % 2 else -0.3) for i in range(40)]      # rumore di +-0.3 attorno a 10
    relative = WarmupDetector(1, ("a",), t=3, eps=0.1, confirm=2, mode="mean")                 # 10% di 10 = 1
    absolute = WarmupDetector(1, ("a",), t=3, eps=0.1, confirm=2, mode="mean", absTol=0.01)    # eps ignorato
    feed(relative, noisy)
    feed(absolute, noisy)
    assert relative.warmupDone
    assert not absolute.warmupDone


def test_invalid_parameters():
    with pytest.raises(ValueError):
        WarmupDetector(10, mode="foo")
    with pytest.raises(ValueError):
        WarmupDetector(10, t=1, mode="slope")
    with pytest.raises(ValueError):
        WarmupDetector(0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
