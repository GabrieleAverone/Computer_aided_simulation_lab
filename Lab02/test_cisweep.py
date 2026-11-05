"""Test di CISweep (eseguibili con pytest, oppure `python test_cisweep.py`)."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import CISweep
from Analysis import meanAndCI


def makeDf(values=None):
    rows = []
    rng = np.random.default_rng(0)
    for nTaxi in (6, 8):
        for rebalance in (True, False):
            run = f"r{nTaxi}{rebalance}"
            for rep in range(10):
                rows.append(dict(runId=run, replica=rep, nTaxi=nTaxi, rebalance=rebalance, nStand=2,
                                 avgWaitInLoco=rng.normal(10 - nTaxi, 1), stable=nTaxi == 8))
    return pd.DataFrame(rows)


def test_varying_params_only_lists_changing_columns():
    assert CISweep.varyingParams(makeDf()) == ["nTaxi", "rebalance"]


def test_summarize_matches_meanAndCI():
    df = makeDf()
    s = CISweep.summarize(df, ["avgWaitInLoco"])
    row = s[s.runId == "r6True"].iloc[0]
    mean, ci = meanAndCI(df[df.runId == "r6True"]["avgWaitInLoco"].tolist())
    assert row["avgWaitInLoco_mean"] == pytest.approx(mean)
    assert row["avgWaitInLoco_ci"] == pytest.approx(ci, rel=1e-3)      # la tabella t ha 3 decimali
    assert row["avgWaitInLoco_rel"] == pytest.approx(ci / abs(mean), rel=1e-3)
    assert row["n"] == 10


def test_confidence_level_changes_width():
    df = makeDf()
    w95 = CISweep.summarize(df, ["avgWaitInLoco"], 0.95)["avgWaitInLoco_ci"]
    w99 = CISweep.summarize(df, ["avgWaitInLoco"], 0.99)["avgWaitInLoco_ci"]
    ratio = stats.t.ppf(0.995, 9) / stats.t.ppf(0.975, 9)
    assert (w99 / w95).tolist() == pytest.approx([ratio] * 4)


def test_single_replica_gives_nan_ci():
    df = makeDf()
    one = df[df.replica == 0]
    s = CISweep.summarize(one, ["avgWaitInLoco"])
    assert s["avgWaitInLoco_ci"].isna().all()


def test_sweep_builds_one_series_per_other_param():
    t = CISweep.sweep(makeDf(), "nTaxi", "avgWaitInLoco")
    assert sorted(t["series"].unique()) == ["rebalance=False", "rebalance=True"]
    assert len(t) == 4
    assert t.groupby("series")["nTaxi"].apply(list).tolist() == [[6, 8], [6, 8]]


def test_sweep_only_stable_drops_unstable_runs():
    t = CISweep.sweep(makeDf(), "nTaxi", "avgWaitInLoco", onlyStable=True)
    assert set(t["nTaxi"]) == {8}


def test_sweep_unknown_param():
    with pytest.raises(ValueError):
        CISweep.sweep(makeDf(), "boh", "avgWaitInLoco")


def test_coverage_is_about_95_percent():
    """Su dati normali con media nota l'IC al 95% deve contenere la media vera ~95% delle volte."""
    rng = np.random.default_rng(1)
    hits = 0
    for _ in range(2000):
        df = pd.DataFrame({"runId": "r", "x": rng.normal(5, 2, 10)})
        s = CISweep.summarize(df, ["x"], groupBy=[])
        hits += abs(s["x_mean"][0] - 5) <= s["x_ci"][0]
    assert 0.93 < hits / 2000 < 0.97


def test_plot_runs():
    import matplotlib
    matplotlib.use("Agg")
    t = CISweep.sweep(makeDf(), "nTaxi", "avgWaitInLoco")
    ax = CISweep.plotSweep(t, "nTaxi", "avgWaitInLoco")
    assert ax.get_xlabel() == "nTaxi"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
