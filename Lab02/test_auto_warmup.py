"""Test del warm-up automatico (eseguibili con pytest, oppure `python test_auto_warmup.py`)."""

import pytest

from Metrics import Metrics
from Simulation import Simulation
from TaxiStand import TaxiStands


def makeStands():
    stands = TaxiStands([2, 2], [(0, 0), (50, 50)])
    stands.distributeTaxi(2, policy="uniform")
    return stands


def test_restart_measurement_discards_everything_before():
    stands = makeStands()
    m = Metrics([(0, 0), (50, 50)], warmup=0, endTime=1000)
    m.update(100, stands)
    m.incrementUserCounter(100)
    m.recordInLocoWait((0, 0), 5, 100)
    m.restartMeasurement(100)

    assert m.warmup == 100
    assert m.nUsers == 0 and m.nUserInLoco == 0 and m.waitedInLocoAcc == 0
    assert sum(m.idleTaxiAccPerStand.values()) == 0
    assert len(m.segEnds) == 1                       # le serie a tratti restano complete
    m.update(300, stands)                            # 200 unità di tempo con 2 taxi fermi
    assert sum(m.idleTaxiAccPerStand.values()) == 2 * 200
    assert m.globalReport(2, stands)["avgQueueInLoco"] == 0.0


STABLE = dict(nTaxi=11, nStand=3, maxTime=50000, verbose=False)


def test_auto_warmup_starts_measuring_when_detector_fires(tmp_path):
    r = Simulation(outDir=str(tmp_path)).run(nReplications=3, seed=1, **STABLE)
    for end, start in zip(r["warmupEndTimes"], r["warmupStartTimes"]):
        assert end is not None
        assert start == end > 100                     # più tardi del warm-up minimo di default


def test_without_auto_warmup_the_fixed_time_is_used(tmp_path):
    r = Simulation(outDir=str(tmp_path)).run(nReplications=3, seed=1, autoWarmup=False, **STABLE)
    assert r["warmupStartTimes"] == [100, 100, 100]


def test_fixed_warmup_is_a_minimum(tmp_path):
    r = Simulation(outDir=str(tmp_path)).run(nReplications=2, seed=1, warmupTime=20000, **STABLE)
    assert all(start >= 20000 for start in r["warmupStartTimes"])


def test_detector_not_firing_falls_back_to_fixed_warmup(tmp_path):
    r = Simulation(outDir=str(tmp_path)).run(nReplications=2, seed=1, warmupWindow=10**9, **STABLE)
    assert r["warmupEndTimes"] == [None, None]
    assert r["warmupStartTimes"] == [100, 100]


def test_detection_is_the_same_with_or_without_auto_warmup(tmp_path):
    on = Simulation(outDir=str(tmp_path / "a")).run(nReplications=2, seed=3, **STABLE)
    off = Simulation(outDir=str(tmp_path / "b")).run(nReplications=2, seed=3, autoWarmup=False, **STABLE)
    assert on["warmupEndTimes"] == off["warmupEndTimes"]      # il detector non dipende dalle metriche


def test_results_csv_has_warmup_end_column(tmp_path):
    import csv
    r = Simulation(outDir=str(tmp_path)).run(nReplications=3, seed=1, **STABLE)
    with open(tmp_path / "results.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [int(row["warmupEnd"]) for row in rows] == r["warmupStartTimes"]


def test_old_results_csv_without_warmup_end_is_completed(tmp_path):
    import csv
    sim = Simulation(outDir=str(tmp_path))
    sim.run(nReplications=2, seed=1, **STABLE)
    path = tmp_path / "results.csv"
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in rows[0] if c != "warmupEnd"]          # simula un file di una versione precedente
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    sim.run(nReplications=2, seed=2, **STABLE)
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["warmupEnd"] == "" for r in rows] == [True, True, False, False]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
