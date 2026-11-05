"""Welch sulla configurazione più carica + istante rilevato dal detector.
Uso: python validate_warmup.py [R] [w] [arrivalRate]"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from Simulation import Simulation

R = int(sys.argv[1]) if len(sys.argv) > 1 else 10
w = int(sys.argv[2]) if len(sys.argv) > 2 else 100
rate = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8     # arrivalRate più alto (clienti/min)

sim = Simulation(outDir="results", nTaxi=4, arrivalRate=rate, warmupAuto=True)
seeds = np.random.SeedSequence(123).spawn(R)
series, ends = [], []
sim.p = sim.baseParams
for s in seeds:
    sim.runReplica(s)
    series.append(sim.tickSeries[0])            # clienti in attesa per tick (si ferma alla rilevazione)
    ends.append(sim.warmupDetector.warmup_end)
    print("warmup_end:", ends[-1], "stationary:", sim.warmupDetector.stationary)

n = min(len(x) for x in series)
Y = np.array([x[:n] for x in series], dtype=float)
mean = Y.mean(axis=0)
ma = np.convolve(mean, np.ones(2 * w + 1) / (2 * w + 1), mode="valid")
found = [e for e in ends if e is not None]

plt.fill_between(range(n), Y.min(0), Y.max(0), alpha=0.2, label="min-max repliche")
plt.plot(mean, lw=0.5, label="media tra repliche")
plt.plot(np.arange(w, n - w), ma, label=f"media mobile w={w}")
if found:
    plt.axvline(np.mean(found), color="r", ls="--", label=f"warmup_end medio = {np.mean(found):.0f}")
plt.xlabel("tick"); plt.ylabel("clienti in attesa"); plt.legend()
import os; os.makedirs("results", exist_ok=True)
plt.savefig("results/welch_warmup.png", dpi=120)
print(f"rilevate {len(found)}/{R} repliche; grafico: results/welch_warmup.png")
