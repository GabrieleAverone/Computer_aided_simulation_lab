
import numpy as np
from collections.abc import Sequence
from User import User
from helpers import manhattanDistance

"""

    TO-DO:
        - implementare calcolo posizione taxi su dove si trova il taxi quando un cliente chiama

"""

class TaxiStand:

    def __init__(self, location: tuple[int, int], capacity: int):

        self.location = location
        self.capacity = capacity
        self.nTaxi = 0
        self.userQueue: list[User] = []


    # ---------------------------- taxi ----------------------------

    def hasFreeSpot(self) -> bool:

        if self.nTaxi == self.capacity: return False
        return True


    def hasIdleTaxi(self) -> bool:

        if self.nTaxi > 0: return True
        return False


    def insertTaxi(self):
        self.nTaxi += 1


    def getTaxi(self):
        self.nTaxi -= 1


    def getCapacity(self) -> int:
        return self.capacity


    def assignTaxis(self, nTaxi: int) -> None:
        self.nTaxi += nTaxi


    # ---------------------------- users ----------------------------

    def hasWaitingUser(self) -> bool:

        if len(self.userQueue) > 0: return True
        else: return False


    def getUser(self) -> User:

        if len(self.userQueue) > 0:
            return self.userQueue.pop(0)
        else:
            raise ValueError


    def insertUser(self, user: User) -> None:

        self.userQueue.append(user)


    def getNextUserTime(self) -> int:

        return self.userQueue[0].getArrivalToStandTime()


    def __str__(self):
        return f"{self.location} -- {self.nTaxi}"

    def __repr__(self) -> str:
        return f"Location: {self.location} -- idleTaxi: {self.nTaxi} -- queue: {len(self.userQueue)}"




class TaxiStands():

    def __init__(self, capacity, standsLocations: Sequence[tuple[int, int]]):

        if len(standsLocations) != len(capacity):
            raise ValueError("The vector standsLocations and capacity must be the same size")

        self.nStands = len(capacity)
        self.stands: dict[tuple[int, int], TaxiStand] = {}

        for i in range(self.nStands):
            self.stands[standsLocations[i]] = TaxiStand(standsLocations[i], capacity[i])

        self.standsCoordsArray = np.array(standsLocations)
        self.standsLocations = standsLocations

        self.totalCapacity = 0
        for cap in capacity:
            self.totalCapacity += cap

        self.totalIdleTaxi = 0
        self.onlineQueue: list[User] = []
        self.totalInLoco = 0

        # taxi vuoti in viaggio verso ciascuno stand (servono per la redistribuzione)
        self.incomingTaxi: dict[tuple[int, int], int] = {loc: 0 for loc in standsLocations}


    def distributeTaxi(self, nTaxi: int, policy: str) -> None:

        self.totalIdleTaxi = nTaxi
        if nTaxi > self.totalCapacity:
            raise ValueError("# of taxi > Total capacity")

        if policy == "uniform":
            remaining = nTaxi
            taxiPerStand = nTaxi // self.nStands

            for location in self.standsLocations:
                nAssigned = min(taxiPerStand, self.stands[location].getCapacity())
                self.stands[location].assignTaxis(nAssigned)
                remaining -= nAssigned

            while remaining > 0:
                for location in self.standsLocations:
                    if remaining == 0:
                        break
                    if self.stands[location].hasFreeSpot():
                        self.stands[location].assignTaxis(1)
                        remaining -= 1

        else: raise ValueError("Policy non recognised")


    # ---------------------------- stand search ----------------------------

    def walkToStand(self, location: tuple[int, int]) -> tuple[int, int]:
        # il cliente va nello stand più vicino, senza sapere se ci sono taxi
        pos = np.array(location, dtype=int)

        dist = np.abs(pos[0] - self.standsCoordsArray[:, 0]) + np.abs(pos[1] - self.standsCoordsArray[:, 1])

        i = int(np.argmin(dist))
        return self.stands[(int(self.standsCoordsArray[i, 0]), int(self.standsCoordsArray[i, 1]))].location


    def findIdleStand(self, location: tuple[int, int]) -> tuple[int, int]:
        # lo stand più vicino con almeno un taxi libero
        pos = np.array(location, dtype=int)

        dist = np.abs(pos[0] - self.standsCoordsArray[:, 0]) + np.abs(pos[1] - self.standsCoordsArray[:, 1])
        validStands = np.array([self.stands[(int(x), int(y))].hasIdleTaxi() for x, y in self.standsCoordsArray])

        if not validStands.any():
            raise ValueError  # nessun taxi libero: il chiamante mette lo user in onlineQueue

        i = np.flatnonzero(validStands)[np.argmin(dist[validStands])]
        return self.stands[(int(self.standsCoordsArray[i, 0]), int(self.standsCoordsArray[i, 1]))].location


    def findFreeStand(self, location: tuple[int, int]) -> tuple[int, int]:
        # come findIdleStand, ma cerca lo stand più vicino con posti liberi
        pos = np.array(location, dtype=int)

        dist = np.abs(pos[0] - self.standsCoordsArray[:, 0]) + np.abs(pos[1] - self.standsCoordsArray[:, 1])
        validStands = np.array([self.stands[(int(x), int(y))].hasFreeSpot() for x, y in self.standsCoordsArray])

        if not validStands.any():
            raise ValueError

        i = np.flatnonzero(validStands)[np.argmin(dist[validStands])]
        return self.stands[(int(self.standsCoordsArray[i, 0]), int(self.standsCoordsArray[i, 1]))].location


    # ------------------------- redistribuzione -------------------------

    def taxiHeadingToStand(self, standLocation: tuple[int, int]) -> None:
        # un taxi vuoto è partito verso questo stand
        self.incomingTaxi[standLocation] += 1


    def taxiArrivedAtStand(self, standLocation: tuple[int, int]) -> None:
        # un taxi vuoto è arrivato (o viene reindirizzato altrove)
        self.incomingTaxi[standLocation] -= 1


    def unmetDemand(self, standLocation: tuple[int, int]) -> int:
        # clienti in coda non ancora "coperti" da un taxi già in arrivo
        return len(self.stands[standLocation].userQueue) - self.incomingTaxi[standLocation]


    def findDemandStand(self, location: tuple[int, int]) -> tuple[int, int] | None:
        # lo stand più vicino con domanda non coperta, None se non ce ne sono
        best = None
        bestDist = 0
        for loc in self.standsLocations:
            if self.unmetDemand(loc) > 0:
                d = manhattanDistance(location, loc)
                if best is None or d < bestDist:
                    best, bestDist = loc, d
        return best


    def findSurplusStand(self, location: tuple[int, int]) -> tuple[int, int] | None:
        # lo stand più vicino con almeno un taxi libero e senza clienti in coda
        best = None
        bestDist = 0
        for loc in self.standsLocations:
            stand = self.stands[loc]
            if stand.hasIdleTaxi() and not stand.hasWaitingUser():
                d = manhattanDistance(location, loc)
                if best is None or d < bestDist:
                    best, bestDist = loc, d
        return best
    def findDonorStand(self, location: tuple[int, int], reserve: int) -> tuple[int, int] | None:
        # ribilanciamento: lo stand più vicino a 'location' con più di 'reserve' taxi fermi.
        # Restituisce None se nessuno stand può cedere un taxi (caso normale, non un errore).
        pos = np.array(location, dtype=int)

        dist = np.abs(pos[0] - self.standsCoordsArray[:, 0]) + np.abs(pos[1] - self.standsCoordsArray[:, 1])
        validStands = np.array([self.stands[(int(x), int(y))].nTaxi > reserve for x, y in self.standsCoordsArray])

        if not validStands.any():
            return None

        i = np.flatnonzero(validStands)[np.argmin(dist[validStands])]
        return self.stands[(int(self.standsCoordsArray[i, 0]), int(self.standsCoordsArray[i, 1]))].location


    # ---------------------------- taxi ----------------------------

    def taxiArrival(self, standLocation: tuple[int, int]) -> bool:
        if self.stands[standLocation].hasFreeSpot():
            self.stands[standLocation].insertTaxi()
            self.totalIdleTaxi += 1
            return True
        else:
            return False  # stand pieno: il chiamante usa findFreeStand per reindirizzare il taxi


    def taxiDeparture(self, standLocation: tuple[int, int]):

        if self.stands[standLocation].hasIdleTaxi():
            self.totalIdleTaxi -= 1
            self.stands[standLocation].getTaxi()
            return True

        raise ValueError


    def existsIdleTaxi(self) -> bool:
        if self.totalIdleTaxi > 0:
            return True
        return False


    def isIdle(self, standLocation: tuple[int, int]) -> bool:
        return self.stands[standLocation].hasIdleTaxi()


    def hasFreeSpot(self, standLocation: tuple[int, int]) -> bool:

        return self.stands[standLocation].hasFreeSpot()


    # ---------------------------- users ----------------------------

    def insertInLocoUser(self, standLocation: tuple[int, int], user: User) -> None:

        self.totalInLoco += 1
        self.stands[standLocation].insertUser(user)


    def insertOnlineUser(self, user: User) -> None:

        self.onlineQueue.append(user)


    def getUser(self, standLocation: tuple[int, int]) -> tuple[User, bool]:

        if len(self.onlineQueue) == 0:
            self.totalInLoco -= 1
            return self.stands[standLocation].getUser(), True

        if not self.stands[standLocation].hasWaitingUser():
            return self.onlineQueue.pop(0), False

        inLocoTime = self.stands[standLocation].getNextUserTime()
        if inLocoTime <= self.onlineQueue[0].getTaxiCallTime():
            self.totalInLoco -= 1
            return self.stands[standLocation].getUser(), True
        else:
            return self.onlineQueue.pop(0), False


    def getOnlineUser(self) -> User:

        return self.onlineQueue.pop(0)


    def hasOnlineUser(self) -> bool:
        if len(self.onlineQueue) > 0: return True

        return False


    def hasWaitingUser(self, standLocation: tuple[int, int]) -> bool:

        return len(self.onlineQueue) > 0 or self.stands[standLocation].hasWaitingUser()
    
    
    def getTotalOnline(self) -> int:
        return len(self.onlineQueue)
    
    
    def getTotalInLoco(self) -> int:
        return self.totalInLoco


    def __str__(self):
        return f"TaxiStands: {self.stands.values()}\nOnlineQueue: {self.onlineQueue}"