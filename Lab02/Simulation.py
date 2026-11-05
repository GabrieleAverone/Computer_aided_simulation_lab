import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

from TaxiStand import TaxiStands
from User import User
from Events import Event
from FutureEventSet import FutureEventSet
from Metrics import Metrics
from WarmupDetector import WarmupDetector
import Output
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


MAX_PLACEMENT_ATTEMPTS = 10_000     # tentativi massimi per piazzare gli stand


# ============================== PARAMETERS ==============================

@dataclass
class Parameters:
    """Tutti i parametri di una simulazione (i valori qui sono i default)."""

    # taxi e stand
    nStand: int = 2
    nTaxi: int = 6
    capacitySlack: int = 0              # posti extra per stand oltre ceil(nTaxi / nStand)
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

    # durata
    maxTime: int = 50000
    warmupTime: int = 100               # transitorio iniziale escluso dalle statistiche (con autoWarmup: warm-up minimo)
    autoWarmup: bool = True             # quando il detector segnala la fine del warm-up (dopo warmupTime), le metriche ripartono da lì;
                                        # se non segnala nulla vale warmupTime. False = sempre warmupTime fisso
    warmupWindow: int = 500             # warm-up detector: eventi per finestra
    warmupT: int = 5                    # warm-up detector: finestre precedenti di riferimento
    warmupEps: float = 0.5              # warm-up detector: tolleranza relativa sulla differenza delle medie
    warmupDelta: float = 1.0            # warm-up detector: soglia minima del denominatore (evita /0)
    warmupConfirm: int = 2              # warm-up detector: finestre stabili consecutive per segnalare la fine

    def capacityList(self) -> list[int]:
        # i posti minimi per far stare tutti i taxi, più il margine capacitySlack
        return [math.ceil(self.nTaxi / self.nStand) + self.capacitySlack] * self.nStand

    def arrivalProb(self) -> float:
        return self.arrivalRate * TIME_STEP_MIN

    def validate(self) -> None:
        if not 0 < self.arrivalProb() <= 1:
            raise ValueError("arrivalRate * TIME_STEP_MIN deve essere in (0, 1]")
        if not 0 <= self.warmupTime < self.maxTime:
            raise ValueError("serve 0 <= warmupTime < maxTime")
        if self.warmupWindow < 1 or self.warmupT < 1 or self.warmupConfirm < 1:
            raise ValueError("warmupWindow, warmupT e warmupConfirm devono essere >= 1")
        if self.warmupT < 2:
            raise ValueError("il test sulla pendenza richiede warmupT >= 2")
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

    Seed: se seed=None (default) a ogni chiamata viene estratto un seed nuovo, quindi due
    chiamate di fila danno risultati diversi. Il seed usato è scritto nel CSV e restituito:
    passandolo a run(seed=...) si riottengono esattamente gli stessi risultati. Con lo stesso
    seed in run diverse (es. in una grid search) si confrontano configurazioni diverse sugli
    stessi numeri casuali.
    """

    def __init__(self, outDir: str = "results", **params) -> None:
        self.outDir = Path(outDir)
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


    # ============================== API PUBBLICA ==============================

    def run(self, nReplications: int = 10, seed: int | None = None, verbose: bool = True,
            returnSeries: bool = False, **overrides) -> dict:
        """Lancia nReplications repliche con i parametri di base modificati da overrides
        (solo per questa run) e salva i risultati. Restituisce un dizionario con
        runId, seed, params, replicas (report globali), mean.

          returnSeries : True = nel risultato anche `stateSeries` (serie a tratti costanti di ogni replica,
                         per i grafici del warm-up detector)
        """
        self.p = replace(self.baseParams, **overrides)      # TypeError se un nome non esiste
        self.p.validate()

        seedSeq = np.random.SeedSequence(seed)               # seed=None: entropia nuova a ogni chiamata
        replicaSeeds = seedSeq.spawn(nReplications)          # un flusso indipendente per replica
        runId = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"    # data + suffisso casuale: unico

        self.outDir.mkdir(parents=True, exist_ok=True)

        globalReports, stateSeries, warmupMeans, warmupEnds, warmupEndTimes = [], [], [], [], []
        warmupStarts = []
        for replicaSeed in replicaSeeds:
            globalReports.append(self.runReplica(replicaSeed))
            warmupMeans.append(self.warmupDetector.windowMeans)
            warmupEnds.append(self.warmupDetector.detectionTime)   # None = non rilevata
            warmupStarts.append(self.metrics.warmup)               # inizio effettivo della finestra di misura
            warmupEndTimes.append(self.warmupDetector.windowEndTimes)
            if returnSeries:
                stateSeries.append(self.metrics.stateSeries())

        Output.saveResults(self.outDir, self.p, runId, seedSeq.entropy, globalReports, warmupStarts) # type: ignore

        mean = {key: sum(g[key] for g in globalReports) / nReplications for key in globalReports[0]}

        if verbose:
            print(f"=== Run {runId}: {nReplications} repliche, seed {seedSeq.entropy} (media) ===")
            print(f"    parametri: {asdict(self.p)}")
            for key in mean:
                print(f"    {key}: {mean[key]:.4f}")

        return {"runId": runId, "seed": seedSeq.entropy, "params": asdict(self.p), "warmupEndTimes": warmupEnds, "warmupStartTimes": warmupStarts, "warmupWindowMeans": warmupMeans, "warmupWindowEndTimes": warmupEndTimes,
                "stateSeries": stateSeries if returnSeries else None, "replicas": globalReports, "mean": mean}



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
            if attempts > MAX_PLACEMENT_ATTEMPTS:
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
        self.FES.insertEvent(nextEvent)
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
        self.FES.insertEvent(self.createSpawnEvent(newSpawnTime))

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
            self.FES.insertEvent(arrivalToStand)

        else:
            if self.taxiStands.existsIdleTaxi():
                standLocation = self.taxiStands.findIdleStand(currentUser.getSpawnLocation())
                timeToUser = getTimeByTaxi(standLocation, currentUser.getSpawnLocation())
                arrivalTime = time + timeToUser
                self.taxiStands.taxiDeparture(standLocation)
                currentUser.setCallTaxiTime(time)
                self.metrics.incrementTimeToUser(time, timeToUser)
                currentUser.setNextLocation(currentUser.getSpawnLocation())
                arrivalToUser = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, currentUser.getSpawnLocation(), currentUser)
                self.FES.insertEvent(arrivalToUser)

            else:
                self.taxiStands.insertOnlineUser(currentUser)
                currentUser.setCallTaxiTime(time)


    def handleUserArrivalToStand(self, time: int, currentEvent: Event) -> None:

        currentUser = self.getEventUser(currentEvent)
        standLocation = currentEvent.getLocation()

        if self.taxiStands.isIdle(standLocation):
            timeToDestination = getTimeByTaxi(standLocation, currentUser.getDestination())
            arrivalTime = time + timeToDestination

            self.taxiStands.taxiDeparture(standLocation)
            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
            self.FES.insertEvent(nextEvent)
            self.metrics.recordInLocoWait(0, time)
            self.metrics.incrementRideTimeAcc(time, timeToDestination)

        else:
            self.taxiStands.insertInLocoUser(standLocation, currentUser)

            # ribilanciamento: solo se la coda non è già coperta da un taxi in arrivo
            if self.p.rebalance and self.taxiStands.unmetDemand(standLocation) > 0:
                self.rebalanceTaxi(time, standLocation)


    def rebalanceTaxi(self, time: int, standLocation: tuple[int, int]) -> None:
        """Un cliente è entrato in coda in uno stand senza taxi: chiama un taxi
        dallo stand più vicino che ne ha più di rebalanceReserve fermi."""
        donorLocation = self.taxiStands.findDonorStand(standLocation, self.p.rebalanceReserve)
        if donorLocation is None:
            return

        self.taxiStands.taxiDeparture(donorLocation)
        self.sendTaxiToStand(time, donorLocation, standLocation, rebalance=True)


    def handleTaxiArrivalToUser(self, time: int, currentEvent: Event) -> None:

        currentUser = self.getEventUser(currentEvent)
        self.metrics.recordOnLineWait(time - currentUser.getTaxiCallTime(), time)

        timeToDestination = getTimeByTaxi(currentEvent.getLocation(), currentUser.getDestination())
        arrivalTime = time + timeToDestination

        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
        self.metrics.incrementRideTimeAcc(time, timeToDestination)
        self.FES.insertEvent(nextEvent)


    def handleArrivalToDestination(self, time: int, currentEvent: Event) -> None:

        currentUser = self.getEventUser(currentEvent)
        self.metrics.incrementRideCounter(time)      # la corsa è completata

        if self.p.onlinePriority and self.taxiStands.hasOnlineUser():
            nextUser = self.taxiStands.getOnlineUser()
            timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSpawnLocation())
            arrivalTime = time + timeToUser

            nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, nextUser.getSpawnLocation(), nextUser)
            self.FES.insertEvent(nextEvent)
            self.metrics.incrementTimeToUser(time, timeToUser)

        else:
            targetStand = self.taxiStands.findDemandStand(currentEvent.getLocation()) if self.p.redistribution else None
            if targetStand is not None:
                self.metrics.incrementRedistribution(time)
            else:
                targetStand = self.taxiStands.findFreeStand(currentEvent.getLocation())
            self.sendTaxiToStand(time, currentEvent.getLocation(), targetStand)


    def handleTaxiArrivalToStand(self, time: int, currentEvent: Event) -> None:

        standLocation = currentEvent.getLocation()
        self.taxiStands.taxiArrivedAtStand(standLocation)

        if self.taxiStands.hasWaitingUser(standLocation):

            nextUser, inLocoFlag = self.taxiStands.getUser(standLocation)

            if inLocoFlag:
                destination = nextUser.getDestination()
                self.metrics.recordInLocoWait(time - nextUser.getArrivalToStandTime(), time)
                timeToDestination = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToDestination

                nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, destination, nextUser)
                self.FES.insertEvent(nextEvent)
                self.metrics.incrementRideTimeAcc(time, timeToDestination)

            else:
                destination = nextUser.getSpawnLocation()
                timeToUser = getTimeByTaxi(standLocation, destination)
                arrivalTime = time + timeToUser

                nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, destination, nextUser)
                self.FES.insertEvent(nextEvent)
                self.metrics.incrementTimeToUser(time, timeToUser)
                
                if self.p.rebalance and self.taxiStands.unmetDemand(standLocation) > 0:
                    self.rebalanceTaxi(time, standLocation)

        elif self.taxiStands.hasFreeSpot(standLocation):
            self.taxiStands.taxiArrival(standLocation)

        else:
            nextStandLocation = self.taxiStands.findFreeStand(standLocation)
            self.sendTaxiToStand(time, standLocation, nextStandLocation)


    # ============================ SINGOLA REPLICA ============================

    def runReplica(self, seed: np.random.SeedSequence) -> dict:
        """Esegue una replica e restituisce il report globale."""
        setSeed(seed)
        Event._counter = 0      # numerazione di eventi e utenti da 0 in ogni replica
        User._counter = 0

        # Simulation Initialization:
        standsCoord = self.placeStands()

        self.taxiStands = TaxiStands(self.p.capacityList(), standsCoord)
        self.taxiStands.distributeTaxi(self.p.nTaxi)

        self.metrics = Metrics(standsCoord, self.p.warmupTime, self.p.maxTime)
        self.warmupDetector = WarmupDetector(self.p.warmupWindow, t=self.p.warmupT, eps=self.p.warmupEps,
                                              delta=self.p.warmupDelta, confirm=self.p.warmupConfirm)

        self.FES = FutureEventSet()
        self.FES.insertEvent(self.createSpawnEvent(0))

        while True:
            currentEvent = self.FES.getEvent()
            time = currentEvent.getTime()

            if time > self.p.maxTime:
                self.metrics.update(self.p.maxTime, self.taxiStands)   # chiude l'ultimo intervallo a maxTime
                break

            self.metrics.update(time, self.taxiStands)
            wasDone = self.warmupDetector.warmupDone
            self.warmupDetector.update(time, {
                "queueInLoco": self.taxiStands.getTotalInLoco(),
                "queueOnLine": self.taxiStands.getTotalOnline(),
                "queueTotal": self.taxiStands.getTotalInLoco() + self.taxiStands.getTotalOnline()})
            if self.warmupDetector.warmupDone and not wasDone:
                if self.p.autoWarmup and self.metrics.warmup < time < self.p.maxTime:
                    self.metrics.restartMeasurement(time)

            handler = self.handlers.get(currentEvent.getType())
            if handler is None:
                raise ValueError(f"Evento non gestito: {currentEvent.getType()}")

            handler(time, currentEvent)

        return self.metrics.globalReport(self.p.nTaxi)


if __name__ == "__main__":
    import itertools

    sim = Simulation(outDir="results")

    # una run con i parametri di base
    sim.run(nReplications=10)

    # grid search: una run per ogni combinazione (ogni run ha un seed nuovo;
    # passa seed=... a run() per usare gli stessi numeri casuali in tutte)
    for nTaxi, reachProb in itertools.product([4, 6, 8], [0.3, 0.7]):
        sim.run(nReplications=10, nTaxi=nTaxi, reachProb=reachProb, verbose=False)
