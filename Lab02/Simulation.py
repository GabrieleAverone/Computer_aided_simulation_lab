from typing import TextIO

from TaxiStand import TaxiStands
from User import User
from Events import Event
from FutureEventSet import FutureEventSet
from helpers import (
    coinToss,
    getNewLocation,
    getNewSpawnTime,
    getTimeByFoot,
    getTimeByTaxi,
    manhattanDistance,
)

"""
    TO-DO:
        - aggiungere le statistiche, probabilemte con una classe metrics fatta di contatori o robe del genere

"""


# ============================== PARAMETERS ==============================

LOG = True
LOG_FILE_NAME = "logFile.txt"
LOG_SEPARATOR_LENGTH = 60

# Parameteres for taxi and taxi stands:
N_STAND = 3
N_TAXI = 6
CAPACITY = [2, 2, 2]
POLICY = "uniform"

# Parameters for Users:
REACH_PROB = 0.5
MIN_TRIP_DISTANCE = 10      # distanza minima (Manhattan) tra spawn e destinazione

# Parameters for the simulation:
MAX_TIME = 1000


logFile: TextIO | None = None


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

    else:
        taxiStands.insertInLocoUser(standLocation, currentUser)
        writeLog(f"User inserted in in-loco queue of stand {standLocation}")


def handleTaxiArrivalToUser(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    currentUser = getEventUser(currentEvent)

    timeToDestination = getTimeByTaxi(currentEvent.getLocation(), currentUser.getDestination())
    arrivalTime = time + timeToDestination

    nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, currentUser.getDestination(), currentUser)
    insertAndLogEvent(FES, nextEvent)


def handleArrivalToDestination(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    currentUser = getEventUser(currentEvent)

    if taxiStands.hasOnlineUser():
        nextUser = taxiStands.getOnlineUser()
        writeLog(f"Taxi serves the first user of the online queue: user {nextUser}")
        timeToUser = getTimeByTaxi(currentUser.getDestination(), nextUser.getSpawnLocation())
        arrivalTime = time + timeToUser

        nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, nextUser.getSpawnLocation(), nextUser)
        insertAndLogEvent(FES, nextEvent)

    else:
        nearestTaxiStand = taxiStands.findFreeStand(currentEvent.getLocation())
        writeLog(f"No user in online queue: taxi goes to stand {nearestTaxiStand}")
        timeToStand = getTimeByTaxi(currentEvent.getLocation(), nearestTaxiStand)
        arrivalTime = time + timeToStand

        nextEvent = Event("TAXI_ARRIVAL_TO_STAND", arrivalTime, nearestTaxiStand, None)
        insertAndLogEvent(FES, nextEvent)


def handleTaxiArrivalToStand(time: int, currentEvent: Event, FES: FutureEventSet, taxiStands: TaxiStands) -> None:

    standLocation = currentEvent.getLocation()

    if taxiStands.hasWaitingUser(standLocation):

        nextUser, inLocoFlag = taxiStands.getUser(standLocation)

        if inLocoFlag:
            writeLog(f"Taxi at stand {standLocation} picks up in-loco user {nextUser}")
            destination = nextUser.getDestination()
            timeToDestination = getTimeByTaxi(standLocation, destination)
            arrivalTime = time + timeToDestination

            nextEvent = Event("ARRIVAL_TO_DESTINATION", arrivalTime, destination, nextUser)
            insertAndLogEvent(FES, nextEvent)

        else:
            writeLog(f"Taxi at stand {standLocation} goes to online user {nextUser}")
            destination = nextUser.getSpawnLocation()
            timeToUser = getTimeByTaxi(standLocation, destination)
            arrivalTime = time + timeToUser

            nextEvent = Event("TAXI_ARRIVAL_TO_USER", arrivalTime, destination, nextUser)
            insertAndLogEvent(FES, nextEvent)

    elif taxiStands.hasFreeSpot(standLocation):
        taxiStands.taxiArrival(standLocation)
        writeLog(f"Taxi parked in stand {standLocation}")

    else:
        nextStandLocation = taxiStands.findFreeStand(standLocation)
        writeLog(f"Stand {standLocation} is full: taxi redirected to stand {nextStandLocation}")
        timeToStand = getTimeByTaxi(standLocation, nextStandLocation)
        arrivalTime = time + timeToStand

        nextEvent = Event("TAXI_ARRIVAL_TO_STAND", arrivalTime, nextStandLocation, None)
        insertAndLogEvent(FES, nextEvent)


EVENT_HANDLERS = {
    "CLIENT_SPAWN": handleClientSpawn,
    "USER_ARRIVAL_TO_STAND": handleUserArrivalToStand,
    "TAXI_ARRIVAL_TO_USER": handleTaxiArrivalToUser,
    "ARRIVAL_TO_DESTINATION": handleArrivalToDestination,
    "TAXI_ARRIVAL_TO_STAND": handleTaxiArrivalToStand,
}


# =============================== SIMULATION ===============================

def runSimulation() -> None:
    global logFile

    # Simulation Initialization:
    standsCoord: list[tuple[int, int]] = []
    for i in range(N_STAND):
        standsCoord.append(getNewLocation())

    taxiStands = TaxiStands(CAPACITY, standsCoord)
    taxiStands.distributeTaxi(N_TAXI, policy=POLICY)

    FES = FutureEventSet()
    time = 0
    FES.insertEvent(createSpawnEvent(time))

    if LOG:
        logFile = open(LOG_FILE_NAME, "w")

    try:
        iteration = 0
        while True:

            currentEvent = FES.getEvent()
            time = currentEvent.getTime()
            eventType = currentEvent.getType()

            if LOG:
                logState(iteration, time, FES, taxiStands, currentEvent)

            if time > MAX_TIME:
                writeLog(f"Time {time} > MAX_TIME ({MAX_TIME}): end of the simulation")
                break

            handler = EVENT_HANDLERS.get(eventType)
            if handler is None:
                raise ValueError(f"Evento non gestito: {eventType}")

            handler(time, currentEvent, FES, taxiStands)
            iteration += 1

    finally:
        if logFile is not None:
            logFile.close()
            logFile = None


if __name__ == "__main__":
    runSimulation()
