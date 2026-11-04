import csv
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TextIO
from uuid import uuid4

import matplotlib
matplotlib.use("Agg")           # i grafici vengono solo salvati su file, mai mostrati
import matplotlib.pyplot as plt
import numpy as np

from TaxiStand import TaxiStands
from User import User
from Events import Event
from FutureEventSet import FutureEventSet
from Metrics import Metrics
import Welch
from helpers import (
    ARRIVAL_RATE,
    TIME_STEP_MIN,
    coinToss,
    getNewLocation,
    getNewSpawnTime,
    getTimeByFoot,
    getTimeByTaxi,
    manhattanDistance,
    setSeed,
)


LOG_SEPARATOR_LENGTH = 60


# ============================== PARAMETERS ==============================

@dataclass
class Parameters:
    """Tutti i parametri di una simulazione (i valori qui sono i default)."""

    # taxi e stand
    nStand: int = 2
    nTaxi: int = 6
    capacity: int | list[int] | None = None     # posti per stand: un intero, una lista, o None = automatico
    capacitySlack: int = 0              # con capacity=None: posti extra per stand oltre ceil(nTaxi / nStand)
    policy: str = "uniform"
    redistribution: bool = True         # dopo una corsa il taxi va verso lo stand con clienti in coda
    rebalance: bool = True              # un cliente in coda richiama un taxi fermo da un altro stand
    rebalanceReserve: int = 1           # uno stand cede un taxi solo se ne ha più di questi fermi

    # clienti
    reachProb: float = 0.5              # probabilità che un cliente sia "in loco"
    arrivalRate: float = ARRIVAL_RATE   # clienti al minuto
    minTripDistance: int = 10           # distanza minima (Manhattan) tra spawn e destinazione

    # posizionamento degli stand
    minStandDistance: int = 20          # distanza minima (Manhattan) tra due stand
    maxPlacementAttempts: int = 10_000

    # durata
    maxTime: int = 50000
    warmupTime: int = 100               # transitorio iniziale escluso dalle statistiche

    def capacityList(self) -> list[int]:
        if self.capacity is None:
            # automatico: i posti minimi per far stare tutti i taxi, più il margine capacitySlack
            return [math.ceil(self.nTaxi / self.nStand) + self.capacitySlack] * self.nStand
        if isinstance(self.capacity, int):
            return [self.capacity] * self.nStand
        return list(self.capacity)

    def arrivalProb(self) -> float:
        return self.arrivalRate * TIME_STEP_MIN

    def validate(self) -> None:
        if self.capacity is not None and self.capacitySlack != 0:
            raise ValueError("capacitySlack si usa solo con capacity=None (capacity automatica)")
        if len(self.capacityList()) != self.nStand:
            raise ValueError("capacity deve avere un valore per ogni stand (o essere un intero)")
        if self.nTaxi > sum(self.capacityList()):
            raise ValueError(f"nTaxi ({self.nTaxi}) è maggiore della capienza totale degli stand "
                             f"({sum(self.capacityList())}): aumenta capacity")
        if not 0 < self.arrivalProb() <= 1:
            raise ValueError("arrivalRate * TIME_STEP_MIN deve essere in (0, 1]")
        if not 0 <= self.warmupTime < self.maxTime:
            raise ValueError("serve 0 <= warmupTime < maxTime")


# t di Student, 95% bilaterale, per df = 1..30 (oltre: ~normale)
_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def meanAndCI(values: list[float]) -> tuple[float, float]:
    """Media e semi-ampiezza dell'intervallo di confidenza al 95%."""
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, float("nan")
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    t = _T95[n - 2] if n - 1 <= len(_T95) else 1.96
    return mean, t * (var / n) ** 0.5


# =============================== SIMULATION ===============================

class Simulation:
    """
    Simulatore del servizio taxi.

        sim = Simulation(outDir="results", nTaxi=6)       # parametri di base
        sim.run(nReplications=10)                          # una run con i parametri di base
        sim.run(nReplications=10, nTaxi=8, reachProb=0.7)  # una run con alcuni parametri cambiati

    Ogni run() lancia nReplications repliche indipendenti e salva in outDir:
        - results.csv: UNA riga per replica, per tutte le run (viene sempre aggiunto in fondo)
        - plots/<runId>_warmup.png: grafico del warm-up della run (linea rossa = warm-up stimato)
        - plots/<runId>_raw.png: dati grezzi, una curva per replica (attese e taxi fermi per intervallo)
        - plots/<runId>_welch_<metrica>.png: metodo di Welch, uno per metrica (con welch=True)
        - plots/<runId>_warmup_from_l.png: medie cumulative ripartite da l (con cumulativeFromWarmup=True)
        - warmup_estimates.csv: warm-up (MSER-5), controllo di stabilità e stima finale, per run e metrica
        - logs/<runId>.txt: log della prima replica (solo con log=True)

    Seed: se seed=None (default) a ogni chiamata viene estratto un seed nuovo, quindi due
    chiamate di fila danno risultati diversi. Il seed usato è scritto nel CSV e restituito:
    passandolo a run(seed=...) si riottengono esattamente gli stessi risultati. Con lo stesso
    seed in run diverse (es. in una grid search) si confrontano configurazioni diverse sugli
    stessi numeri casuali.
    """

    def __init__(self, outDir: str = "results", log: bool = False, **params) -> None:
        self.outDir = Path(outDir)
        self.log = log
        self.baseParams = Parameters(**params)
        self.baseParams.validate()

        self.handlers = {
            "CLIENT_SPAWN": self.handleClientSpawn,
            "USER_ARRIVAL_TO_STAND": self.handleUserArrivalToStand,
            "TAXI_ARRIVAL_TO_USER": self.handleTaxiArrivalToUser,
            "ARRIVAL_TO_DESTINATION": self.handleArrivalToDestination,
            "TAXI_ARRIVAL_TO_STAND": self.handleTaxiArrivalToStand,
        }

        # stato della replica in corso
        self.p: Parameters
        self.metrics: Metrics
        self.taxiStands: TaxiStands
        self.FES: FutureEventSet
        self.logFile: TextIO | None = None


    # ============================== API PUBBLICA ==============================

    def run(self, nReplications: int = 10, seed: int | None = None, verbose: bool = True,
            welch: bool = True, welchDelta: int = 100, welchWs: tuple[int, ...] = (2, 5, 10, 20),
            warmup: int | None = None, cumulativeFromWarmup: bool = False,
            rawPlot: bool = True, **overrides) -> dict:
        """Lancia nReplications repliche con i parametri di base modificati da overrides
        (solo per questa run) e salva i risultati. Restituisce un dizionario con
        runId, seed, params, replicas (report globali), standReports, mean, ci, welch.

        Analisi del warm-up (non cambia results.csv, che usa sempre warmupTime):
          welch                 : metodo di Welch + MSER-5 + controllo di stabilità + stima finale
          welchDelta, welchWs   : ampiezza degli intervalli (passi) e semi-ampiezze w delle medie mobili
          warmup                : warm-up l scelto a mano (passi); None = stima automatica (max di MSER-5)
          cumulativeFromWarmup  : salva anche le medie cumulative ripartite da l (verifica della "pancia")
          rawPlot               : salva plots/<runId>_raw.png con i dati veri di ogni replica (una curva per replica):
                                  attesa in loco, attesa online, taxi fermi, mediati su intervalli di welchDelta passi
        """
        self.p = replace(self.baseParams, **overrides)      # TypeError se un nome non esiste
        self.p.validate()

        seedSeq = np.random.SeedSequence(seed)               # seed=None: entropia nuova a ogni chiamata
        replicaSeeds = seedSeq.spawn(nReplications)          # un flusso indipendente per replica
        runId = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"    # data + suffisso casuale: unico

        self.outDir.mkdir(parents=True, exist_ok=True)
        logPath = self.outDir / "logs" / f"{runId}.txt" if self.log else None

        globalReports, standReports, warmupSeries, stateSeries, waitSeries = [], [], [], [], []
        for i, replicaSeed in enumerate(replicaSeeds):
            g, s = self.runReplica(replicaSeed, logPath if i == 0 else None)
            globalReports.append(g)
            standReports.append(s)
            warmupSeries.append(self.metrics.warmupSeries())
            if welch or rawPlot:
                stateSeries.append(self.metrics.stateSeries())
            if rawPlot:
                waitSeries.append(self.metrics.waitSeries())

        welchResult = self.analyzeWarmup(stateSeries, welchDelta, welchWs, warmup) if welch else None
        mark = welchResult["warmup"] if welchResult else None

        self.saveResults(runId, seedSeq.entropy, globalReports) # type: ignore
        self.saveWarmupPlot(runId, seedSeq.entropy, warmupSeries, overrides, welchResult) # type: ignore
        if rawPlot:
            self.saveRawPlot(runId, seedSeq.entropy, stateSeries, waitSeries, welchDelta, mark, overrides) # type: ignore
        if welchResult:
            self.saveWelchPlots(runId, seedSeq.entropy, welchResult, overrides) # type: ignore
            self.saveWarmupEstimates(runId, seedSeq.entropy, welchResult, nReplications) # type: ignore
            if cumulativeFromWarmup and mark is not None:
                self.saveWarmupFromPlot(runId, seedSeq.entropy, stateSeries, mark, overrides) # type: ignore

        mean, ci = {}, {}
        for key in globalReports[0]:
            mean[key], ci[key] = meanAndCI([g[key] for g in globalReports])

        if verbose:
            print(f"=== Run {runId}: {nReplications} repliche, seed {seedSeq.entropy} (media ± IC95%) ===")
            print(f"    parametri: {asdict(self.p)}")
            for key in mean:
                print(f"    {key}: {mean[key]:.4f} ± {ci[key]:.4f}")
            if welchResult:
                self.printWelch(welchResult)

        return {"runId": runId, "seed": seedSeq.entropy, "params": asdict(self.p),
                "replicas": globalReports, "standReports": standReports, "mean": mean, "ci": ci,
                "welch": None if welchResult is None else {k: v for k, v in welchResult.items() if k != "analysis"}}


    # ============================ WARM-UP (WELCH) ============================

    def analyzeWarmup(self, stateSeries: list[dict], delta: int, ws: tuple[int, ...], manualWarmup: int | None) -> dict:
        """Welch + MSER-5 + controllo di stabilità + stima finale (replication/deletion).
        status: "ok" (l stimato), "unstable" (nessun warm-up restituito), "manual" (l passato a mano)."""
        a = Welch.analyze(stateSeries, self.p.maxTime, delta, ws)
        if manualWarmup is not None:
            l, status = manualWarmup, "manual"
        elif a["unstable"]:
            l, status = None, "unstable"
        else:
            l, status = a["warmup"], "ok"

        estimate = None
        if l is not None:
            if not 0 <= l < self.p.maxTime:
                raise ValueError("warmup deve essere in [0, maxTime)")
            means = Welch.deletionMeans(stateSeries, l, self.p.maxTime)
            estimate = {key: dict(zip(("mean", "ci"), meanAndCI(vals))) for key, vals in means.items()}

        return {"warmup": l, "status": status, "unstable": a["unstable"], "delta": delta, "ws": a["ws"],
                "mser": {k: r["l"] for k, r in a["mser"].items()},
                "mserAtLimit": [k for k, r in a["mser"].items() if r["atLimit"]],
                "trend": a["trend"], "estimate": estimate, "analysis": a}


    def printWelch(self, r: dict) -> None:
        print(f"    --- warm-up (Welch, delta={r['delta']}, MSER-5) ---")
        for k in Welch.METRICS:
            t = r["trend"][k]
            flag = "  <-- trend crescente" if t["unstable"] else ""
            print(f"    {k}: MSER-5 l={r['mser'][k]}, 2a metà: livello {t['level']:.3f}, "
                  f"aumento {t['rise']:+.3f} (pendenza {t['slope']:.2e}/passo, t={t['t']:.2f}){flag}")
        if r["mserAtLimit"]:
            print(f"    attenzione: MSER-5 sul limite massimo per {r['mserAtLimit']} (warm-up non ben determinato)")
        if r["status"] == "unstable":
            print("    ESITO: probabilmente instabile / nessuno stato stazionario -> nessun warm-up restituito")
            return
        origin = "manuale" if r["status"] == "manual" else "max tra le metriche"
        print(f"    ESITO: warm-up l = {r['warmup']} passi ({origin})"
              + ("  [ATTENZIONE: la configurazione sembra instabile]" if r["unstable"] else ""))
        print("    stima replication/deletion (media ± IC95%, dati dopo l):")
        for k, e in r["estimate"].items():
            print(f"      {k}: {e['mean']:.4f} ± {e['ci']:.4f}")


    # ================================ OUTPUT ================================

    def saveResults(self, runId: str, seed: int, globalReports: list[dict]) -> None:
        """Aggiunge a results.csv una riga per replica (un solo file per tutte le run)."""
        params = asdict(self.p)
        params["capacity"] = "-".join(str(c) for c in self.p.capacityList())
        columns = ["runId", "replica", "seed"] + list(params) + list(globalReports[0])

        path = self.outDir / "results.csv"
        if path.exists() and path.stat().st_size > 0:
            with open(path, newline="") as f:
                oldColumns = next(csv.reader(f))
            if oldColumns != columns:
                raise ValueError(f"{path} ha colonne diverse da quelle attuali: "
                                 "cambia outDir o rinomina il vecchio file")
        else:
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(columns)

        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            for i, g in enumerate(globalReports):
                writer.writerow({"runId": runId, "replica": i, "seed": seed, **params, **g})


    def saveWarmupPlot(self, runId: str, seed: int, warmupSeries: list[dict], overrides: dict,
                       welchResult: dict | None = None) -> None:
        """Salva plots/<runId>_warmup.png: una curva per replica (sottili) e la media (spessa).
        Nel titolo ci sono i parametri passati a run() (quelli della grid search).
        La linea rossa è il warm-up stimato (Welch/MSER-5) o passato a mano; se la configurazione
        è instabile non c'è linea. Senza analisi di Welch è warmupTime, come prima."""
        if welchResult is None:
            mark, note = self.p.warmupTime, "fine del warm-up"
        elif welchResult["warmup"] is None:
            mark, note = None, "configurazione probabilmente instabile: nessun warm-up"
        else:
            mark, note = welchResult["warmup"], "warm-up " + ("manuale" if welchResult["status"] == "manual" else "stimato")
        grid = np.arange(1, self.p.maxTime + 1)
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

        plotsDir = self.outDir / "plots"
        plotsDir.mkdir(parents=True, exist_ok=True)
        fig.savefig(plotsDir / f"{runId}_warmup.png", dpi=120)
        plt.close(fig)


    def _titleText(self, runId: str, seed: int, overrides: dict, what: str) -> str:
        paramsText = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "parametri di base"
        return f"{what} -- {runId}\n{paramsText}\nseed {seed}"


    def saveWelchPlots(self, runId: str, seed: int, r: dict, overrides: dict) -> None:
        """Salva plots/<runId>_welch_<metrica>.png, uno per metrica: Ybar (sottile, trasparente)
        e le medie mobili di Welch per ogni w. Asse x in passi di simulazione (centro dell'intervallo).
        Linea rossa = warm-up della configurazione; linea grigia punteggiata = MSER-5 della metrica."""
        a = r["analysis"]
        labels = {"idleTaxi": "taxi fermi", "queueInLoco": "coda in loco", "queueOnLine": "coda online"}
        x = Welch.intervalCenters(a["m"], a["delta"])
        plotsDir = self.outDir / "plots"
        plotsDir.mkdir(parents=True, exist_ok=True)

        for key, label in labels.items():
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(x, a["ybar"][key], color="gray", alpha=0.35, linewidth=0.8, label="Ybar (media sulle repliche)")
            for i, (w, curve) in enumerate(a["welch"][key].items()):
                ax.plot(x[:len(curve)], curve, color=f"C{i}", linewidth=1.6, label=f"Welch w={w}")
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
            fig.suptitle(self._titleText(runId, seed, overrides, f"Metodo di Welch: {label}"), fontsize=9)
            fig.tight_layout(rect=(0, 0, 1, 0.9))
            fig.savefig(plotsDir / f"{runId}_welch_{key}.png", dpi=120)
            plt.close(fig)


    def saveRawPlot(self, runId: str, seed: int, stateSeries: list[dict], waitSeries: list[dict],
                    delta: int, mark: float | None, overrides: dict) -> None:
        """Salva plots/<runId>_raw.png: i dati veri, una curva (colore) per replica, senza mediare tra
        repliche né smussare. Attese: media delle attese dei clienti serviti in ogni intervallo di
        `delta` passi (buco = nessun cliente servito). Taxi fermi: media nel tempo su ogni intervallo.
        Linea rossa = warm-up stimato/manuale, se c'è."""
        m = self.p.maxTime // delta
        x = Welch.intervalCenters(m, delta)
        panels = [("attesa in loco (passi)", "InLoco"), ("attesa online (passi)", "OnLine"), ("taxi fermi", None)]

        fig, axes = plt.subplots(3, 1, sharex=True, figsize=(8, 7))
        for ax, (label, kind) in zip(axes, panels):
            for j in range(len(stateSeries)):
                if kind is None:
                    y = Welch.binStateSeries(stateSeries[j], "idleTaxi", self.p.maxTime, delta)
                else:
                    w = waitSeries[j]
                    y = Welch.binEventMeans(w["times" + kind], w["waits" + kind], self.p.maxTime, delta)
                ax.plot(x, y, color=f"C{j % 10}", alpha=0.7, linewidth=0.8)
            if mark is not None:
                ax.axvline(mark, color="red", linestyle="--", linewidth=1)
            ax.set_ylabel(label, fontsize=8)
            ax.grid(True, alpha=0.3)
        axes[-1].set_xlabel(f"tempo (passi); una curva per replica, medie su intervalli di {delta} passi"
                            + ("; linea rossa = warm-up" if mark is not None else ""))
        fig.suptitle(self._titleText(runId, seed, overrides, "Dati per replica"), fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.94))

        plotsDir = self.outDir / "plots"
        plotsDir.mkdir(parents=True, exist_ok=True)
        fig.savefig(plotsDir / f"{runId}_raw.png", dpi=120)
        plt.close(fig)


    def saveWarmupFromPlot(self, runId: str, seed: int, stateSeries: list[dict], l: float, overrides: dict) -> None:
        """Salva plots/<runId>_warmup_from_l.png: come il grafico del warm-up, ma le medie
        cumulative ripartono da l (media su [l, t]). Se l è giusto non c'è più la "pancia" iniziale."""
        grid = np.arange(1, self.p.maxTime + 1, dtype=float)
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
        fig.suptitle(self._titleText(runId, seed, overrides, f"Media cumulativa da l={l:g}"), fontsize=9)
        fig.tight_layout(rect=(0, 0, 1, 0.94))

        plotsDir = self.outDir / "plots"
        plotsDir.mkdir(parents=True, exist_ok=True)
        fig.savefig(plotsDir / f"{runId}_warmup_from_l.png", dpi=120)
        plt.close(fig)


    def saveWarmupEstimates(self, runId: str, seed: int, r: dict, nReplications: int) -> None:
        """Aggiunge a warmup_estimates.csv una riga per metrica (l MSER-5, trend, stima finale)."""
        columns = ["runId", "seed", "nReplications", "metric", "delta", "status", "warmup",
                   "mserL", "trendSlope", "trendT", "trendUnstable", "mean", "ci"]
        path = self.outDir / "warmup_estimates.csv"
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


    # ================================ LOGGING ================================

    def writeLog(self, message: str = "") -> None:
        """Scrive una riga nel file di log (solo se il log della replica è attivo)."""
        if self.logFile is not None:
            self.logFile.write(message + "\n")


    def logState(self, iteration: int, time: int, currentEvent: Event) -> None:
        """Scrive lo stato della simulazione all'inizio di ogni iterazione."""
        self.writeLog()
        self.writeLog("=" * LOG_SEPARATOR_LENGTH)
        self.writeLog(f"Iteration: {iteration} -- Time: {time}")
        self.writeLog("=" * LOG_SEPARATOR_LENGTH)
        self.writeLog(f"FES:\n{self.FES}")
        self.writeLog(f"taxiStands:\n{self.taxiStands}")
        self.writeLog(f"Current event: {currentEvent!r}")

        currentUser = currentEvent.getUser()
        if currentUser is not None:
            self.writeLog(f"Current user: {currentUser.describe()}")


    def insertAndLogEvent(self, event: Event) -> None:
        self.FES.insertEvent(event)
        self.writeLog(f"Event insertion: {event!r}")


    # ============================== HELPERS ==================================

    def createSpawnEvent(self, spawnTime: int) -> Event:
        """Crea un nuovo utente e il relativo evento CLIENT_SPAWN."""
        spawnLocation = getNewLocation()
        destination = getNewLocation()
        while manhattanDistance(spawnLocation, destination) < self.p.minTripDistance:
            spawnLocation = getNewLocation()
            destination = getNewLocation()

        inLoco = coinToss(self.p.reachProb)

        newUser = User(spawnTime, spawnLocation, destination, inLoco)
        return Event("CLIENT_SPAWN", spawnTime, spawnLocation, newUser)


    def placeStands(self) -> list[tuple[int, int]]:
        """Estrae nStand posizioni distinte, a distanza di Manhattan >= minStandDistance."""
        positions: list[tuple[int, int]] = []
        attempts = 0
        while len(positions) < self.p.nStand:
            attempts += 1
            if attempts > self.p.maxPlacementAttempts:
                raise RuntimeError(
                    f"Impossibile piazzare {self.p.nStand} stand con distanza minima {self.p.minStandDistance}: "
                    "riduci minStandDistance o nStand")
            candidate = getNewLocation()
            if all(manhattanDistance(candidate, p) >= self.p.minStandDistance for p in positions):
                positions.append(candidate)
        return positions


    def sendTaxiToStand(self, time: int, fromLocation: tuple[int, int], standLocation: tuple[int, int],
                        rebalance: bool = False) -> None:
        """Manda un taxi vuoto (già fuori da qualsiasi stand) verso uno stand.
        rebalance=True se il viaggio è un ribilanciamento (metrica a parte)."""
        timeToStand = getTimeByTaxi(fromLocation, standLocation)
        nextEvent = Event("TAXI_ARRIVAL_TO_STAND", time + timeToStand, standLocation, None)
        self.taxiStands.taxiHeadingToStand(standLocation)
        self.insertAndLogEvent(nextEvent)
        if rebalance:
            self.metrics.recordRebalance(time, timeToStand)
        else:
            self.metrics.incrementTimeBackToStand(time, timeToStand)


    @staticmethod
    def getEventUser(event: Event) -> User:
        user = event.getUser()
        if user is None:
            raise ValueError(f"User is not defined for {event.getType()} type event")
        return user


    # ============================ EVENT HANDLERS ============================

    def handleClientSpawn(self, time: int, currentEvent: Event) -> None:

        # schedule next client spawn event
        newSpawnTime = time + getNewSpawnTime(self.p.arrivalProb())
        self.insertAndLogEvent(self.createSpawnEvent(newSpawnTime))

        # Compute user action
        currentUser = self.getEventUser(currentEvent)
        self.metrics.incrementUserCounter(time)

        if currentUser.getInLocoFlag():
            nearestStandLocation = self.taxiStands.walkToStand(currentUser.getSpawnLocation())
            timeToStand = getTimeByFoot(currentUser.getSpawnLocation(), nearestStandLocation)
            arrivalTime = time + timeToStand
            currentUser.setNextLocation(nearestStandLocation)
            currentUser.setArrivalToStandTime(arrivalTime)
            arrivalToStand = Event("USER_ARRIVAL_TO_STAND", arrivalTime, nearestStandLocation, currentUser)
            self.insertAndLogEvent(arrivalToStand)

        else:
            if self.taxiStands.existsIdleTaxi():
                standLocation = self.taxiStands.findIdleStand(currentUser.getSpawnLocation())
                timeToUser = getTimeByTaxi(standLocation, currentUser.getSpawnLocation())
                arrivalTime = time + timeToUser
                self.taxiStands.taxiDeparture(standLocation)
                self.writeLog(f"Taxi departed from stand {standLocation}")
                currentUser.setCallTaxiTime(time)
                self.metrics.incrementTimeToUser(time, timeToUser)
                currentUser.setNextLocation(currentUser.getSpawnLocation())
                arrivalToUser = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, currentUser.getSpawnLocation(), currentUser)
                self.insertAndLogEvent(arrivalToUser)

            else:
                self.taxiStands.insertOnlineUser(currentUser)
                currentUser.setCallTaxiTime(time)
                self.writeLog("User inserted in online queue")


    def handleUserArrivalToStand(self, time: int, currentEvent: Event) -> None:

        currentUser = self.getEventUser(currentEvent)
        standLocation = currentEvent.getLocation()

        if self.taxiStands.isIdle(standLocation):
            timeToDestination = getTimeByTaxi(standLocation, currentUser.getDestination())
            arrivalTime = time + timeToDestination

            self.taxiStands.taxiDeparture(standLocation)
            self.writeLog(f"Taxi departed from stand {standLocation}")
            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
            self.insertAndLogEvent(nextEvent)
            self.metrics.recordInLocoWait(standLocation, 0, time)
            self.metrics.incrementRideTimeAcc(time, timeToDestination)

        else:
            self.taxiStands.insertInLocoUser(standLocation, currentUser)
            self.writeLog(f"User inserted in in-loco queue of stand {standLocation}")

            # ribilanciamento: solo se la coda non è già coperta da un taxi in arrivo
            if self.p.rebalance and self.taxiStands.unmetDemand(standLocation) > 0:
                self.rebalanceTaxi(time, standLocation)


    def rebalanceTaxi(self, time: int, standLocation: tuple[int, int]) -> None:
        """Un cliente è entrato in coda in uno stand senza taxi: chiama un taxi
        dallo stand più vicino che ne ha più di rebalanceReserve fermi."""
        donorLocation = self.taxiStands.findDonorStand(standLocation, self.p.rebalanceReserve)
        if donorLocation is None:
            self.writeLog("Rebalance: no stand can give a taxi")
            return

        self.taxiStands.taxiDeparture(donorLocation)
        self.writeLog(f"Rebalance: taxi sent from stand {donorLocation} to stand {standLocation}")
        self.sendTaxiToStand(time, donorLocation, standLocation, rebalance=True)


    def handleTaxiArrivalToUser(self, time: int, currentEvent: Event) -> None:

        currentUser = self.getEventUser(currentEvent)
        self.metrics.recordOnLineWait(time - currentUser.getTaxiCallTime(), time)

        timeToDestination = getTimeByTaxi(currentEvent.getLocation(), currentUser.getDestination())
        arrivalTime = time + timeToDestination

        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
        self.metrics.incrementRideTimeAcc(time, timeToDestination)
        self.insertAndLogEvent(nextEvent)


    def handleArrivalToDestination(self, time: int, currentEvent: Event) -> None:

        currentUser = self.getEventUser(currentEvent)
        self.metrics.incrementRideCounter(time)      # la corsa è completata

        if self.taxiStands.hasOnlineUser():
            nextUser = self.taxiStands.getOnlineUser()
            self.writeLog(f"Taxi serves the first user of the online queue: user {nextUser}")
            timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSpawnLocation())
            arrivalTime = time + timeToUser

            nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, nextUser.getSpawnLocation(), nextUser)
            self.insertAndLogEvent(nextEvent)
            self.metrics.incrementTimeToUser(time, timeToUser)

        else:
            targetStand = self.taxiStands.findDemandStand(currentEvent.getLocation()) if self.p.redistribution else None
            if targetStand is not None:
                self.writeLog(f"No user in online queue: taxi goes to stand {targetStand} (users waiting)")
                self.metrics.incrementRedistribution(time)
            else:
                targetStand = self.taxiStands.findFreeStand(currentEvent.getLocation())
                self.writeLog(f"No user in online queue: taxi goes to stand {targetStand}")
            self.sendTaxiToStand(time, currentEvent.getLocation(), targetStand)


    def handleTaxiArrivalToStand(self, time: int, currentEvent: Event) -> None:

        standLocation = currentEvent.getLocation()
        self.taxiStands.taxiArrivedAtStand(standLocation)

        if self.taxiStands.hasWaitingUser(standLocation):

            nextUser, inLocoFlag = self.taxiStands.getUser(standLocation)

            if inLocoFlag:
                self.writeLog(f"Taxi at stand {standLocation} picks up in-loco user {nextUser}")
                destination = nextUser.getDestination()
                self.metrics.recordInLocoWait(standLocation, time - nextUser.getArrivalToStandTime(), time)
                timeToDestination = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToDestination

                nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, destination, nextUser)
                self.insertAndLogEvent(nextEvent)
                self.metrics.incrementRideTimeAcc(time, timeToDestination)

            else:
                self.writeLog(f"Taxi at stand {standLocation} goes to online user {nextUser}")
                destination = nextUser.getSpawnLocation()
                timeToUser = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToUser

                nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, destination, nextUser)
                self.insertAndLogEvent(nextEvent)
                self.metrics.incrementTimeToUser(time, timeToUser)
                
                if self.p.rebalance and self.taxiStands.unmetDemand(standLocation) > 0:
                    self.rebalanceTaxi(time, standLocation)

        elif self.taxiStands.hasFreeSpot(standLocation):
            self.taxiStands.taxiArrival(standLocation)
            self.writeLog(f"Taxi parked in stand {standLocation}")

        else:
            nextStandLocation = self.taxiStands.findFreeStand(standLocation)
            self.writeLog(f"Stand {standLocation} is full: taxi redirected to stand {nextStandLocation}")
            self.sendTaxiToStand(time, standLocation, nextStandLocation)


    # ============================ SINGOLA REPLICA ============================

    def runReplica(self, seed: np.random.SeedSequence, logPath: Path | None = None) -> tuple[dict, dict]:
        """Esegue una replica e restituisce (report globale, report per stand)."""
        setSeed(seed)
        Event._counter = 0      # numerazione di eventi e utenti da 0 in ogni replica (log leggibili)
        User._counter = 0

        # Simulation Initialization:
        standsCoord = self.placeStands()

        self.taxiStands = TaxiStands(self.p.capacityList(), standsCoord)
        self.taxiStands.distributeTaxi(self.p.nTaxi, policy=self.p.policy)

        self.metrics = Metrics(standsCoord, self.p.warmupTime, self.p.maxTime)

        self.FES = FutureEventSet()
        self.FES.insertEvent(self.createSpawnEvent(0))

        if logPath is not None:
            logPath.parent.mkdir(parents=True, exist_ok=True)
            self.logFile = open(logPath, "w")

        try:
            iteration = 0
            while True:

                currentEvent = self.FES.getEvent()
                time = currentEvent.getTime()

                if self.logFile is not None:
                    self.logState(iteration, time, currentEvent)

                if time > self.p.maxTime:
                    self.metrics.update(self.p.maxTime, self.taxiStands)   # chiude l'ultimo intervallo a maxTime
                    self.writeLog(f"Time {time} > maxTime ({self.p.maxTime}): end of the simulation")
                    break

                self.metrics.update(time, self.taxiStands)

                handler = self.handlers.get(currentEvent.getType())
                if handler is None:
                    raise ValueError(f"Evento non gestito: {currentEvent.getType()}")

                handler(time, currentEvent)
                iteration += 1

        finally:
            if self.logFile is not None:
                self.logFile.close()
                self.logFile = None

        return self.metrics.globalReport(self.p.nTaxi, self.taxiStands), self.metrics.standReport()


if __name__ == "__main__":
    import itertools

    sim = Simulation(outDir="results", log=True)

    # una run con i parametri di base
    sim.run(nReplications=10)

    # grid search: una run per ogni combinazione (ogni run ha un seed nuovo;
    # passa seed=... a run() per usare gli stessi numeri casuali in tutte)
    # (capacity non è indicata: viene calcolata da nTaxi e nStand)
    for nTaxi, reachProb in itertools.product([4, 6, 8], [0.3, 0.7]):
        sim.run(nReplications=10, nTaxi=nTaxi, reachProb=reachProb, verbose=False)
