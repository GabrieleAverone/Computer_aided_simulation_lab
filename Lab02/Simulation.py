import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TextIO
from uuid import uuid4

import numpy as np

from TaxiStand import TaxiStands
from User import User
from Events import Event
from FutureEventSet import FutureEventSet
from Metrics import Metrics
from WarmupDetector import WarmupDetector
import Analysis
import Output
from Analysis import meanAndCI
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
    onlinePriority: bool = True         # dopo una corsa il taxi va prima da un cliente online in coda; False = torna a uno stand

    # clienti
    reachProb: float = 0.5              # probabilità che un cliente sia "in loco"
    arrivalRate: float = ARRIVAL_RATE   # clienti al minuto
    minTripDistance: int = 20           # distanza minima (Manhattan) tra spawn e destinazione

    # posizionamento degli stand
    minStandDistance: int = 40          # distanza minima (Manhattan) tra due stand
    maxPlacementAttempts: int = 10_000

    # durata
    maxTime: int = 50000
    warmupTime: int = 100               # transitorio iniziale escluso dalle statistiche
    warmupWindow: int = 500             # warm-up detector: eventi per finestra
    warmupT: int = 5                    # warm-up detector: finestre precedenti di riferimento
    warmupEps: float = 0.05             # warm-up detector: tolleranza relativa sulla differenza delle medie
    warmupDelta: float = 1.0            # warm-up detector: soglia minima del denominatore (evita /0)
    warmupConfirm: int = 2              # warm-up detector: finestre stabili consecutive per segnalare la fine

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
        if self.warmupWindow < 1 or self.warmupT < 1 or self.warmupConfirm < 1:
            raise ValueError("warmupWindow, warmupT e warmupConfirm devono essere >= 1")
        if self.warmupEps <= 0 or self.warmupDelta <= 0:
            raise ValueError("warmupEps e warmupDelta devono essere > 0")


# =============================== SIMULATION ===============================

class Simulation:
    """
    Simulatore del servizio taxi.

        sim = Simulation(outDir="results", nTaxi=6)       # parametri di base
        sim.run(nReplications=10)                          # una run con i parametri di base
        sim.run(nReplications=10, nTaxi=8, reachProb=0.7)  # una run con alcuni parametri cambiati

    Ogni run() lancia nReplications repliche indipendenti e salva in outDir:
        - results.csv: UNA riga per replica, per tutte le run (viene sempre aggiunto in fondo)
        - plots/<parametri>/<runId>_welch_<metrica>.png: metodo di Welch, uno per metrica (con welch=True)
          (<parametri> = i parametri passati a run(), es. nTaxi=6_reachProb=0.3; "base" se non ce ne sono)
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
        self.warmupDetector: WarmupDetector
        self.taxiStands: TaxiStands
        self.FES: FutureEventSet
        self.logFile: TextIO | None = None
        self.plotsDir: Path = self.outDir / "plots"     # cartella dei grafici della run in corso


    # ============================== API PUBBLICA ==============================

    def run(self, nReplications: int = 10, seed: int | None = None, verbose: bool = True,
            welch: bool = True, welchDelta: int = 100, welchWs: tuple[int, ...] = (1, 2, 5, 10, 20),
            trendRelTol: float | None = None, trendAbsTol: float | None = None,
            plotFolders: bool = True, **overrides) -> dict:
        """Lancia nReplications repliche con i parametri di base modificati da overrides
        (solo per questa run) e salva i risultati. Restituisce un dizionario con
        runId, seed, params, replicas (report globali), standReports, mean, ci, welch.

        Analisi di stabilità (non cambia i risultati in results.csv, tranne la colonna `stable`):
          welch                 : grafici di Welch + controllo di stabilità a blocchi per replica
                                  (colonne `stable` per replica e `pUnstable` per configurazione in results.csv)
          welchDelta, welchWs   : ampiezza degli intervalli (passi) e semi-ampiezze w delle medie mobili
          trendRelTol, trendAbsTol : soglie del controllo (None = default di Welch.blockCheckRow: 0.25, 2.0 clienti).
                                  La 2a metà della run è divisa in 4 blocchi: una replica è instabile se, per almeno una
                                  coda (in loco / online), le medie dei blocchi crescono sempre e l'aumento
                                  (ultimo - primo) supera max(trendRelTol * livello medio, trendAbsTol)
          plotFolders           : True = i grafici di ogni run vanno in plots/<parametri>/ (es. plots/nTaxi=6_reachProb=0.3/);
                                  False = tutti insieme in plots/
        """
        self.p = replace(self.baseParams, **overrides)      # TypeError se un nome non esiste
        self.p.validate()

        seedSeq = np.random.SeedSequence(seed)               # seed=None: entropia nuova a ogni chiamata
        replicaSeeds = seedSeq.spawn(nReplications)          # un flusso indipendente per replica
        runId = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"    # data + suffisso casuale: unico

        self.outDir.mkdir(parents=True, exist_ok=True)
        self.plotsDir = Output.makePlotsDir(self.outDir, overrides, plotFolders)
        logPath = self.outDir / "logs" / f"{runId}.txt" if self.log else None

        globalReports, standReports, stateSeries, warmupMeans, warmupEnds = [], [], [], [], []
        for i, replicaSeed in enumerate(replicaSeeds):
            g, s = self.runReplica(replicaSeed, logPath if i == 0 else None)
            globalReports.append(g)
            standReports.append(s)
            warmupMeans.append(self.warmupDetector.windowMeans)
            warmupEnds.append(self.warmupDetector.detectionTime)   # None = non rilevata
            if welch:
                stateSeries.append(self.metrics.stateSeries())

        thresholds = {"relTol": trendRelTol, "absTol": trendAbsTol}
        thresholds = {k: v for k, v in thresholds.items() if v is not None}
        welchResult = (Analysis.analyzeStability(stateSeries, self.p.maxTime, welchDelta, welchWs, **thresholds)
                       if welch else None)

        # per results.csv (vuoto senza welch): `stable` per replica, `pUnstable` per configurazione
        stable = None if welchResult is None else [not bool(u) for u in welchResult["unstableReplicas"]]
        pUnstable = None if welchResult is None else welchResult["pUnstable"]
        Output.saveResults(self.outDir, self.p, runId, seedSeq.entropy, globalReports, stable, pUnstable) # type: ignore
        if welchResult:
            Output.saveWelchPlots(self.plotsDir, runId, seedSeq.entropy, welchResult, overrides) # type: ignore

        mean, ci = {}, {}
        for key in globalReports[0]:
            mean[key], ci[key] = meanAndCI([g[key] for g in globalReports])

        if verbose:
            print(f"=== Run {runId}: {nReplications} repliche, seed {seedSeq.entropy} (media ± IC95%) ===")
            print(f"    parametri: {asdict(self.p)}")
            for key in mean:
                print(f"    {key}: {mean[key]:.4f} ± {ci[key]:.4f}")
            if welchResult:
                Analysis.printWelch(welchResult)

        return {"runId": runId, "seed": seedSeq.entropy, "params": asdict(self.p), "plotsDir": str(self.plotsDir),
                "warmupEndTimes": warmupEnds, "warmupWindowMeans": warmupMeans, "replicas": globalReports, "standReports": standReports, "mean": mean, "ci": ci,
                "welch": None if welchResult is None else {k: v for k, v in welchResult.items() if k != "analysis"}}



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

        if self.p.onlinePriority and self.taxiStands.hasOnlineUser():
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
        self.warmupDetector = WarmupDetector(self.p.warmupWindow, t=self.p.warmupT, eps=self.p.warmupEps,
                                              delta=self.p.warmupDelta, confirm=self.p.warmupConfirm)

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
                wasDone = self.warmupDetector.warmupDone
                if self.warmupDetector.update(time, {
                        "queueInLoco": self.taxiStands.getTotalInLoco(),
                        "queueOnLine": self.taxiStands.getTotalOnline()}):
                    self.writeLog(f"Warm-up detector, window {self.warmupDetector.nWindows - 1} closed: "
                                  f"{ {v: m[-1] for v, m in self.warmupDetector.windowMeans.items()} }")
                    if self.warmupDetector.warmupDone and not wasDone:
                        self.writeLog(f"Warm-up detector: END OF WARM-UP signalled at time {time} "
                                      f"(window {self.warmupDetector.detectionWindow})")

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
