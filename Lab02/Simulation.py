from typing import TextIO

from TaxiStand import TaxiStands
from User import User
from Events import Event
from FutureEventSet import FutureEventSet
from Metrics import Metrics
from helpers import (
    coinToss,
    getNewLocation,
    getNewSpawnTime,
    getTimeByFoot,
    getTimeByTaxi,
    manhattanDistance,
    setSeed,
)



# ============================== PARAMETERS ==============================

LOG = True
LOG_FILE_NAME = "logFile.txt"
LOG_SEPARATOR_LENGTH = 60

# Parameteres for taxi and taxi stands:
N_STAND = 2
N_TAXI = 6
CAPACITY = [3, 3]
POLICY = "uniform"
REDISTRIBUTION = True       # dopo una corsa il taxi va verso lo stand con clienti in coda

# Parameters for Users:
REACH_PROB = 0.5
MIN_TRIP_DISTANCE = 10      # distanza minima (Manhattan) tra spawn e destinazione

# Parameters for the stands placement:
MIN_STAND_DISTANCE = 20     # distanza minima (Manhattan) tra due stand
MAX_PLACEMENT_ATTEMPTS = 10_000

# Parameters for the simulation:
MAX_TIME = 1000
WARMUP_TIME = 100           # transitorio iniziale escluso dalle statistiche
N_REPLICATIONS = 10         # repliche indipendenti (seed = BASE_SEED + i)
BASE_SEED = 0

# Parameters for rebalancing:
REBALANCE = True            # attiva/disattiva il ribilanciamento dei taxi
REBALANCE_RESERVE = 1       # uno stand cede un taxi solo se ne ha più di questi fermi


logFile: TextIO | None = None
metrics: Metrics


# ================================ LOGGING ================================

def writeLog(message: str = "") -> None:
    """Scrive una riga nel file di log (solo se LOG è attivo)."""
    if LOG and logFile is not None:
        logFile.write(message + "\n")


def logState(iteration: int, time: int, FES: FutureEventSet, taxiStands: TaxiStands, currentEvent: Event) -> None:
    """Scrive lo stato della simulazione all'inizio di ogni iterazione."""
    writeLog()
    writeLog("=" * LOG_SEPARATOR_LENGTH)
    writeLog(f"Iteration: {iteration} -- Time: {time}")
    writeLog("=" * LOG_SEPARATOR_LENGTH)
    writeLog(f"FES:\n{FES}")
    writeLog(f"taxiStands:\n{taxiStands}")
    writeLog(f"Current event: {currentEvent!r}")

    currentUser = currentEvent.getUser()
    if currentUser is not None:
        writeLog(f"Current user: {currentUser.describe()}")


def insertAndLogEvent(FES: FutureEventSet, event: Event) -> None:
    FES.insertEvent(event)
    writeLog(f"Event insertion: {event!r}")


# ============================== HELPERS ==================================

def createSpawnEvent(spawnTime: int) -> Event:
    """Crea un nuovo utente e il relativo evento CLIENT_SPAWN."""
    spawnLocation = getNewLocation()
    destination = getNewLocation()
    while manhattanDistance(spawnLocation, destination) < MIN_TRIP_DISTANCE:
        spawnLocation = getNewLocation()
        destination = getNewLocation()

    inLoco = coinToss(REACH_PROB)

    newUser = User(spawnTime, spawnLocation, destination, inLoco)
    return Event("CLIENT_SPAWN", spawnTime, spawnLocation, newUser)


def placeStands() -> list[tuple[int, int]]:
    """Estrae N_STAND posizioni distinte, a distanza di Manhattan >= MIN_STAND_DISTANCE."""
    positions: list[tuple[int, int]] = []
    attempts = 0
    while len(positions) < N_STAND:
        attempts += 1
        if attempts > MAX_PLACEMENT_ATTEMPTS:
            raise RuntimeError(
                f"Impossibile piazzare {N_STAND} stand con distanza minima {MIN_STAND_DISTANCE}: "
                "riduci MIN_STAND_DISTANCE o N_STAND")
        candidate = getNewLocation()
        if all(manhattanDistance(candidate, p) >= MIN_STAND_DISTANCE for p in positions):
            positions.append(candidate)
    return positions


def sendTaxiToStand(time: int, fromLocation: tuple[int, int], standLocation: tuple[int, int],
                    FES: FutureEventSet, taxiStands: TaxiStands, rebalance: bool = False) -> None:
    """Manda un taxi vuoto (già fuori da qualsiasi stand) verso uno stand.
    rebalance=True se il viaggio è un ribilanciamento (metrica a parte)."""
    timeToStand = getTimeByTaxi(fromLocation, standLocation)
    nextEvent = Event("TAXI_ARRIVAL_TO_STAND", time + timeToStand, standLocation, None)
    taxiStands.taxiHeadingToStand(standLocation)
    insertAndLogEvent(FES, nextEvent)
    if rebalance:
        metrics.recordRebalance(time, timeToStand)
    else:
        metrics.incrementTimeBackToStand(time, timeToStand)


def getEventUser(event: Event) -> User:
    user = event.getUser()
    if user is None:
        raise ValueError(f"User is not defined for {event.getType()} type event")
    return user


# ============================ EVENT HANDLERS ============================

def handleClientSpawn(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    # schedule next client spawn event
    newSpawnTime = time + getNewSpawnTime()
    insertAndLogEvent(FES, createSpawnEvent(newSpawnTime))

    # Compute user action
    currentUser = getEventUser(currentEvent)
    metrics.incrementUserCounter(time)

    if currentUser.getInLocoFlag():
        nearestStandLocation = taxiStands.walkToStand(currentUser.getSpawnLocation())
        timeToStand = getTimeByFoot(currentUser.getSpawnLocation(), nearestStandLocation)
        arrivalTime = time + timeToStand
        currentUser.setNextLocation(nearestStandLocation)
        currentUser.setArrivalToStandTime(arrivalTime)
        arrivalToStand = Event("USER_ARRIVAL_TO_STAND", arrivalTime, nearestStandLocation, currentUser)
        insertAndLogEvent(FES, arrivalToStand)

    else:
        if taxiStands.existsIdleTaxi():
            standLocation = taxiStands.findIdleStand(currentUser.getSpawnLocation())
            timeToUser = getTimeByTaxi(standLocation, currentUser.getSpawnLocation())
            arrivalTime = time + timeToUser
            taxiStands.taxiDeparture(standLocation)
            writeLog(f"Taxi departed from stand {standLocation}")
            currentUser.setCallTaxiTime(time)
            metrics.incrementTimeToUser(time, timeToUser)
            currentUser.setNextLocation(currentUser.getSpawnLocation())
            arrivalToUser = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, currentUser.getSpawnLocation(), currentUser)
            insertAndLogEvent(FES, arrivalToUser)

        else:
            taxiStands.insertOnlineUser(currentUser)
            currentUser.setCallTaxiTime(time)
            writeLog("User inserted in online queue")


def handleUserArrivalToStand(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    currentUser = getEventUser(currentEvent)
    standLocation = currentEvent.getLocation()

    if taxiStands.isIdle(standLocation):
        timeToDestination = getTimeByTaxi(standLocation, currentUser.getDestination())
        arrivalTime = time + timeToDestination

        taxiStands.taxiDeparture(standLocation)
        writeLog(f"Taxi departed from stand {standLocation}")
        nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
        insertAndLogEvent(FES, nextEvent)
        metrics.recordInLocoWait(standLocation, 0, time)
        metrics.incrementRideTimeAcc(time, timeToDestination)

    else:
        taxiStands.insertInLocoUser(standLocation, currentUser)
        writeLog(f"User inserted in in-loco queue of stand {standLocation}")

        # ribilanciamento: solo se la coda non è già coperta da un taxi in arrivo
        if REBALANCE and taxiStands.unmetDemand(standLocation) > 0:
            rebalanceTaxi(time, standLocation, FES, taxiStands)


def rebalanceTaxi(time: int, standLocation: tuple[int, int], FES: FutureEventSet, taxiStands: TaxiStands) -> None:
    """Un cliente è entrato in coda in uno stand senza taxi: chiama un taxi
    dallo stand più vicino che ne ha più di REBALANCE_RESERVE fermi."""
    donorLocation = taxiStands.findDonorStand(standLocation, REBALANCE_RESERVE)
    if donorLocation is None:
        writeLog("Rebalance: no stand can give a taxi")
        return

    taxiStands.taxiDeparture(donorLocation)
    writeLog(f"Rebalance: taxi sent from stand {donorLocation} to stand {standLocation}")
    sendTaxiToStand(time, donorLocation, standLocation, FES, taxiStands, rebalance=True)


def handleTaxiArrivalToUser(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    currentUser = getEventUser(currentEvent)
    metrics.recordOnLineWait(time - currentUser.getTaxiCallTime(), time)

    timeToDestination = getTimeByTaxi(currentEvent.getLocation(), currentUser.getDestination())
    arrivalTime = time + timeToDestination

    nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
    metrics.incrementRideTimeAcc(time, timeToDestination)
    insertAndLogEvent(FES, nextEvent)


def handleArrivalToDestination(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    currentUser = getEventUser(currentEvent)
    metrics.incrementRideCounter(time)      # la corsa è completata

    if taxiStands.hasOnlineUser():
        nextUser = taxiStands.getOnlineUser()
        writeLog(f"Taxi serves the first user of the online queue: user {nextUser}")
        timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSpawnLocation())
        arrivalTime = time + timeToUser

        nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, nextUser.getSpawnLocation(), nextUser)
        insertAndLogEvent(FES, nextEvent)
        metrics.incrementTimeToUser(time, timeToUser)

    else:
        targetStand = taxiStands.findDemandStand(currentEvent.getLocation()) if REDISTRIBUTION else None
        if targetStand is not None:
            writeLog(f"No user in online queue: taxi goes to stand {targetStand} (users waiting)")
            metrics.incrementRedistribution(time)
        else:
            targetStand = taxiStands.findFreeStand(currentEvent.getLocation())
            writeLog(f"No user in online queue: taxi goes to stand {targetStand}")
        sendTaxiToStand(time, currentEvent.getLocation(), targetStand, FES, taxiStands)


def handleTaxiArrivalToStand(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    standLocation = currentEvent.getLocation()
    taxiStands.taxiArrivedAtStand(standLocation)

    if taxiStands.hasWaitingUser(standLocation):

        nextUser, inLocoFlag = taxiStands.getUser(standLocation)

        if inLocoFlag:
            writeLog(f"Taxi at stand {standLocation} picks up in-loco user {nextUser}")
            destination = nextUser.getDestination()
            metrics.recordInLocoWait(standLocation, time - nextUser.getArrivalToStandTime(), time)
            timeToDestination = getTimeByTaxi(standLocation, destination)
            arrivalTime = time + timeToDestination

            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, destination, nextUser)
            insertAndLogEvent(FES, nextEvent)
            metrics.incrementRideTimeAcc(time, timeToDestination)

        else:
            writeLog(f"Taxi at stand {standLocation} goes to online user {nextUser}")
            destination = nextUser.getSpawnLocation()
            timeToUser = getTimeByTaxi(standLocation, destination)
            arrivalTime = time + timeToUser

            nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, destination, nextUser)
            insertAndLogEvent(FES, nextEvent)
            metrics.incrementTimeToUser(time, timeToUser)

    elif taxiStands.hasFreeSpot(standLocation):
        taxiStands.taxiArrival(standLocation)
        writeLog(f"Taxi parked in stand {standLocation}")

    else:
        nextStandLocation = taxiStands.findFreeStand(standLocation)
        writeLog(f"Stand {standLocation} is full: taxi redirected to stand {nextStandLocation}")
        sendTaxiToStand(time, standLocation, nextStandLocation, FES, taxiStands)


EVENT_HANDLERS = {
    "CLIENT_SPAWN": handleClientSpawn,
    "USER_ARRIVAL_TO_STAND": handleUserArrivalToStand,
    "TAXI_ARRIVAL_TO_USER": handleTaxiArrivalToUser,
    "ARRIVAL_TO_DESTINATION": handleArrivalToDestination,
    "TAXI_ARRIVAL_TO_STAND": handleTaxiArrivalToStand,
}


# =============================== SIMULATION ===============================

def runSimulation(seed: int | None = None, log: bool = LOG) -> tuple[dict, dict]:
    """Esegue una replica e restituisce (report globale, report per stand)."""
    global logFile
    global metrics

    if seed is not None:
        setSeed(seed)

    # Simulation Initialization:
    standsCoord = placeStands()

    taxiStands = TaxiStands(CAPACITY, standsCoord)
    taxiStands.distributeTaxi(N_TAXI, policy=POLICY)

    metrics = Metrics(standsCoord, WARMUP_TIME, MAX_TIME)

    FES = FutureEventSet()
    time = 0
    FES.insertEvent(createSpawnEvent(time))

    if log and LOG:
        logFile = open(LOG_FILE_NAME, "w")

    try:
        iteration = 0
        while True:

            currentEvent = FES.getEvent()
            time = currentEvent.getTime()
            eventType = currentEvent.getType()

            if logFile is not None:
                logState(iteration, time, FES, taxiStands, currentEvent)

            if time > MAX_TIME:
                metrics.update(MAX_TIME, taxiStands)   # chiude l'ultimo intervallo esattamente a MAX_TIME
                writeLog(f"Time {time} > MAX_TIME ({MAX_TIME}): end of the simulation")
                break

            metrics.update(time, taxiStands)

            handler = EVENT_HANDLERS.get(eventType)
            if handler is None:
                raise ValueError(f"Evento non gestito: {eventType}")

            handler(time, currentEvent, FES, taxiStands)
            iteration += 1

    finally:
        if logFile is not None:
            logFile.close()
            logFile = None

    return metrics.globalReport(N_TAXI, taxiStands), metrics.standReport()


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


def runReplications() -> None:
    globalReports = []
    standReports = []
    for i in range(N_REPLICATIONS):
        # il log viene scritto solo per la prima replica
        g, s = runSimulation(seed=BASE_SEED + i, log=(i == 0))
        globalReports.append(g)
        standReports.append(s)

    print(f"=== Metriche globali ({N_REPLICATIONS} repliche, warm-up {WARMUP_TIME}, "
          f"fine {MAX_TIME}; media ± IC95%) ===")
    for key in globalReports[0]:
        mean, ci = meanAndCI([g[key] for g in globalReports])
        print(f"{key}: {mean:.4f} ± {ci:.4f}")

    # le posizioni degli stand cambiano a ogni replica: il dettaglio per stand
    # si mostra solo per la prima
    print(f"\n=== Metriche per stand (replica 0, seed {BASE_SEED}) ===")
    for pos, values in standReports[0].items():
        print(pos, values)

    metrics.plotWarmup()


if __name__ == "__main__":
    runReplications()
