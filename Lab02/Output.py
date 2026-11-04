"""Salvataggio dei risultati: results.csv, warmup_estimates.csv e grafici (warm-up, Welch, media cumulativa da l).
Funzioni senza stato: ricevono cartelle e parametri della run come argomenti."""

import csv
import re
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")           # i grafici vengono solo salvati su file, mai mostrati
import matplotlib.pyplot as plt
import numpy as np

import Welch

if TYPE_CHECKING:               # solo per le annotazioni (evita l'import circolare con Simulation)
    from Simulation import Parameters


def saveResults(outDir: Path, p: "Parameters", runId: str, seed: int, globalReports: list[dict],
                stable: bool | None = None) -> None:
    """Aggiunge a results.csv una riga per replica (un solo file per tutte le run)."""
    params = asdict(p)
    params["capacity"] = "-".join(str(c) for c in p.capacityList())
    columns = ["runId", "replica", "seed"] + list(params) + list(globalReports[0]) + ["stable"]

    path = outDir / "results.csv"
    if path.exists() and path.stat().st_size > 0:
        with open(path, newline="") as f:
            oldColumns = next(csv.reader(f))
        if oldColumns == columns[:-1]:                      # results.csv di prima di "stable": aggiungo la colonna vuota
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
            with open(path, "w", newline="") as f:
                csv.writer(f).writerows([rows[0] + ["stable"]] + [row + [""] for row in rows[1:]])
        elif oldColumns != columns:
            raise ValueError(f"{path} ha colonne diverse da quelle attuali: "
                             "cambia outDir o rinomina il vecchio file")
    else:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(columns)

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        for i, g in enumerate(globalReports):
            writer.writerow({"runId": runId, "replica": i, "seed": seed, **params, **g,
                                 "stable": "" if stable is None else stable})


def saveWarmupPlot(plotsDir: Path, p: "Parameters", runId: str, seed: int, warmupSeries: list[dict], overrides: dict,
                   welchResult: dict | None = None) -> None:
    """Salva plots/<runId>_warmup.png: una curva per replica (sottili) e la media (spessa).
    Nel titolo ci sono i parametri passati a run() (quelli della grid search).
    La linea rossa è il warm-up stimato (Welch/MSER-5) o passato a mano; se la configurazione
    è instabile non c'è linea. Senza analisi di Welch è warmupTime, come prima."""
    if welchResult is None:
        mark, note = p.warmupTime, "fine del warm-up"
    elif welchResult["status"] == "stable":                 # stabilityOnly: nessun warm-up da mostrare
        mark, note = None, "analisi di sola stabilità: nessun warm-up"
    elif welchResult["warmup"] is None:
        mark, note = None, "configurazione probabilmente instabile: nessun warm-up"
    else:
        mark, note = welchResult["warmup"], "warm-up " + ("manuale" if welchResult["status"] == "manual" else "stimato")
    grid = np.arange(1, p.maxTime + 1)
    labels = {"idleTaxi": "taxi fermi (media cumulativa)",
              "queueInLoco": "coda in loco (media cumulativa)",
              "queueOnLine": "coda online (media cumulativa)"}

    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(8, 7))
    for ax, (key, label) in zip(axes, labels.items()):
        curves = [np.interp(grid, s["times"], s[key]) for s in warmupSeries]
        for curve in curves:
            ax.plot(grid, curve, color="gray", alpha=0.3, linewidth=0.8)
        ax.plot(grid, np.mean(curves, axis=0), color="C0", linewidth=2)
        if mark is not None:
            ax.axvline(mark, color="red", linestyle="--", linewidth=1)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel(f"tempo (passi); linea rossa = {note}")
    paramsText = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "parametri di base"
    fig.suptitle(f"Andamento verso lo stato stazionario -- {runId}\n{paramsText}\nseed {seed}", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    plotsDir.mkdir(parents=True, exist_ok=True)
    fig.savefig(plotsDir / f"{runId}_warmup.png", dpi=120)
    plt.close(fig)


def makePlotsDir(outDir: Path, overrides: dict, perRun: bool) -> Path:
    """Cartella dei grafici di una run: plots/ (perRun=False) oppure plots/<parametri>/, dove
    <parametri> sono i parametri passati a run() (es. nTaxi=6_reachProb=0.3_rebalance=True).
    Se esiste già (stessi parametri in un'altra run) si aggiunge _2, _3, ..."""
    base = outDir / "plots"
    if not perRun:
        return base
    name = "_".join(f"{k}={v}" for k, v in overrides.items()) or "base"
    name = re.sub(r"[^\w=.,+-]+", "-", name)           # niente spazi, slash, parentesi
    path, i = base / name, 2
    while path.exists():
        path = base / f"{name}_{i}"
        i += 1
    return path


def _titleText(runId: str, seed: int, overrides: dict, what: str) -> str:
    paramsText = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "parametri di base"
    return f"{what} -- {runId}\n{paramsText}\nseed {seed}"


def saveWelchPlots(plotsDir: Path, runId: str, seed: int, r: dict, overrides: dict) -> None:
    """Salva plots/<runId>_welch_<metrica>.png, uno per metrica: Ybar (sottile, trasparente)
    e le medie mobili di Welch per ogni w. Asse x in passi di simulazione (centro dell'intervallo).
    Linea rossa = warm-up della configurazione; linea grigia punteggiata = MSER-5 della metrica."""
    a = r["analysis"]
    labels = {"idleTaxi": "taxi fermi", "queueInLoco": "coda in loco", "queueOnLine": "coda online"}
    x = Welch.intervalCenters(a["m"], a["delta"])
    plotsDir.mkdir(parents=True, exist_ok=True)

    for key, label in labels.items():
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(x, a["ybar"][key], color="gray", alpha=0.35, linewidth=0.8, label="Ybar (media sulle repliche)")
        for i, (w, curve) in enumerate(a["welch"][key].items()):
            ax.plot(x[:len(curve)], curve, color=f"C{i}", linewidth=1.6, label=f"Welch w={w}")
        if r["mser"] is not None:
            ax.axvline(r["mser"][key], color="gray", linestyle=":", linewidth=1.2,
                       label=f"MSER-5 ({label}): {r['mser'][key]}")
        if r["warmup"] is not None:
            ax.axvline(r["warmup"], color="red", linestyle="--", linewidth=1, label=f"warm-up: {r['warmup']}")
        ax.set_xlabel(f"tempo (passi); intervalli di {a['delta']} passi")
        ax.set_ylabel(f"{label} (media su intervallo)", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc="best")
        if a["trend"][key]["unstable"]:
            ax.text(0.02, 0.97, "trend crescente nella 2a metà", transform=ax.transAxes,
                    va="top", fontsize=8, color="red")
        if r["status"] == "unstable":
            ax.set_title("configurazione probabilmente instabile / nessuno stato stazionario", fontsize=8, color="red")
        fig.suptitle(_titleText(runId, seed, overrides, f"Metodo di Welch: {label}"), fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.9))
        fig.savefig(plotsDir / f"{runId}_welch_{key}.png", dpi=120)
        plt.close(fig)


def saveWarmupFromPlot(plotsDir: Path, p: "Parameters", runId: str, seed: int, stateSeries: list[dict], l: float, overrides: dict) -> None:
    """Salva plots/<runId>_warmup_from_l.png: come il grafico del warm-up, ma le medie
    cumulative ripartono da l (media su [l, t]). Se l è giusto non c'è più la "pancia" iniziale."""
    grid = np.arange(1, p.maxTime + 1, dtype=float)
    labels = {"idleTaxi": "taxi fermi (da l)",
              "queueInLoco": "coda in loco (da l)",
              "queueOnLine": "coda online (da l)"}

    fig, axes = plt.subplots(3, 1, sharex=True, figsize=(8, 7))
    for ax, (key, label) in zip(axes, labels.items()):
        curves = [Welch.cumulativeMeanFrom(s, key, l, grid) for s in stateSeries]
        for curve in curves:
            ax.plot(grid, curve, color="gray", alpha=0.3, linewidth=0.8)
        ax.plot(grid, np.mean(curves, axis=0), color="C0", linewidth=2)
        ax.axvline(l, color="red", linestyle="--", linewidth=1)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("tempo (passi); linea rossa = fine del warm-up l")
    fig.suptitle(_titleText(runId, seed, overrides, f"Media cumulativa da l={l:g}"), fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    plotsDir.mkdir(parents=True, exist_ok=True)
    fig.savefig(plotsDir / f"{runId}_warmup_from_l.png", dpi=120)
    plt.close(fig)


def saveWarmupEstimates(outDir: Path, runId: str, seed: int, r: dict, nReplications: int) -> None:
    """Aggiunge a warmup_estimates.csv una riga per metrica (l MSER-5, trend, stima finale)."""
    columns = ["runId", "seed", "nReplications", "metric", "delta", "status", "warmup",
               "mserL", "trendSlope", "trendT", "trendUnstable", "mean", "ci"]
    path = outDir / "warmup_estimates.csv"
    newFile = not (path.exists() and path.stat().st_size > 0)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if newFile:
            writer.writeheader()
        for key in Welch.METRICS:
            e = r["estimate"][key] if r["estimate"] else {"mean": "", "ci": ""}
            writer.writerow({"runId": runId, "seed": seed, "nReplications": nReplications, "metric": key,
                             "delta": r["delta"], "status": r["status"],
                             "warmup": "" if r["warmup"] is None else r["warmup"],
                             "mserL": r["mser"][key], "trendSlope": r["trend"][key]["slope"],
                             "trendT": r["trend"][key]["t"], "trendUnstable": r["trend"][key]["unstable"],
                             "mean": e["mean"], "ci": e["ci"]})
