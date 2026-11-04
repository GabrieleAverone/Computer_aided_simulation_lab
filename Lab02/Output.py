"""Salvataggio dei risultati: results.csv e grafici di Welch.
Funzioni senza stato: ricevono cartelle e parametri della run come argomenti."""

import csv
import re
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")           # i grafici vengono solo salvati su file, mai mostrati
import matplotlib.pyplot as plt

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
        if oldColumns != columns:
            # file vecchio: si completa solo se mancano parametri nuovi (valore di default) o `stable` (vuoto)
            defaults = {k: str(v) for k, v in asdict(type(p)()).items()}
            missing = [c for c in columns if c not in oldColumns]
            if [c for c in oldColumns if c not in columns] or any(c not in defaults and c != "stable" for c in missing):
                raise ValueError(f"{path} ha colonne diverse da quelle attuali: "
                                 "cambia outDir o rinomina il vecchio file")
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow({**{c: defaults.get(c, "") for c in missing}, **row})
    else:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(columns)

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        for i, g in enumerate(globalReports):
            writer.writerow({"runId": runId, "replica": i, "seed": seed, **params, **g,
                                 "stable": "" if stable is None else stable})


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
    Se la configurazione è instabile (trend crescente) lo segnala nel grafico."""
    a = r["analysis"]
    labels = {"idleTaxi": "taxi fermi", "queueInLoco": "coda in loco", "queueOnLine": "coda online"}
    x = Welch.intervalCenters(a["m"], a["delta"])
    plotsDir.mkdir(parents=True, exist_ok=True)

    for key, label in labels.items():
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(x, a["ybar"][key], color="gray", alpha=0.35, linewidth=0.8, label="Ybar (media sulle repliche)")
        for i, (w, curve) in enumerate(a["welch"][key].items()):
            ax.plot(x[:len(curve)], curve, color=f"C{i}", linewidth=1.6, label=f"Welch w={w}")
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
