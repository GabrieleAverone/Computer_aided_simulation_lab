
import numpy as np
from collections.abc import Sequence
from User import User

"""
    
    TO-DO:
        - Controllare contatori vari
        - Implementare la ricerca dello stand più vicino in maniera più efficiente ->
                usare
        
"""

class TaxiStand:
    
    def __init__(self, coord: tuple[int, int], capacity: int):
        
        self.pos = coord
        self.capacity = capacity
        self.nTaxi = 0
        self.userQueue: list[User] = []
        
        
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
        
        
    def getCapacity(self) -> int:
        return self.capacity
    
    
    def assignTaxis(self, nTaxi: int) -> None:
        self.nTaxi += nTaxi
        
    def __str__(self):
        return f"{self.pos} -- {self.nTaxi}"
    
    def __repr__(self) -> str:
        return f"Location: {self.pos} -- idleTaxi: {self.nTaxi} -- queue: {len(self.userQueue)}"
        
        
    
    
class TaxiStands():
    
    def __init__(self, capacity, pos: Sequence[tuple[int, int]]):
        
        if len(pos) != len(capacity):
            raise ValueError("The vector pos and capacity must be the same size")
        
        self.nStands = len(capacity)
        self.stands: dict[tuple[int, int], TaxiStand] = {}

        for i in range(self.nStands):
            self.stands[pos[i]] =  TaxiStand(pos[i], capacity[i])
            
        self.coords = np.array(pos)
        self.pos = pos
        
        self.totalCapacity = 0
        for cap in capacity:
            self.totalCapacity += cap
            
        self.totalIdleTaxi = 0
        self.onlineQueue: list[User] = []
        
    
    def distributeTaxi(self, nTaxi: int, policy: str) -> None:
        
        self.totalIdleTaxi = nTaxi
        if nTaxi > self.totalCapacity:
            raise ValueError("# of taxi > Total capacity")
        
        if policy == "uniform":
            remaining = nTaxi
            taxiPerStand = nTaxi // self.nStands

            for p in self.pos:
                n = min(taxiPerStand, self.stands[p].getCapacity())
                self.stands[p].assignTaxis(n)
                remaining -= n

            while remaining > 0:
                for p in self.pos:
                    if remaining == 0:
                        break
                    if self.stands[p].hasFreeSpot():
                        self.stands[p].assignTaxis(1)
                        remaining -= 1
                        
        else: raise ValueError("Policy non recognised")
        
    
    def walkToStand(self, coord: tuple[int, int]) -> tuple[int, int]:
        # il cliente va nello stand più vicino, senza sapere se ci sono taxi
        pos = np.array(coord, dtype=int)

        dist = np.abs(pos[0] - self.coords[:, 0]) + np.abs(pos[1] - self.coords[:, 1])

        i = int(np.argmin(dist))
        return self.stands[(int(self.coords[i, 0]), int(self.coords[i, 1]))].pos
    
    
    def taxiCall(self, coord: tuple[int, int]) -> tuple[int, int]:
        pos = np.array(coord, dtype=int)

        dist = np.abs(pos[0] - self.coords[:, 0]) + np.abs(pos[1] - self.coords[:, 1])
        validi = np.array([self.stands[(int(x), int(y))].hasIdleTaxi() for x, y in self.coords])

        if not validi.any():
            raise ValueError  # nessun taxi libero: il chiamante mette lo user in onlineQueue

        i = np.flatnonzero(validi)[np.argmin(dist[validi])]
        return self.stands[(int(self.coords[i, 0]), int(self.coords[i, 1]))].pos


    def findFreeStand(self, coord: tuple[int, int]) -> tuple[int, int]:
        # come taxiCall, ma cerca lo stand più vicino con posti liberi
        pos = np.array(coord, dtype=int)

        dist = np.abs(pos[0] - self.coords[:, 0]) + np.abs(pos[1] - self.coords[:, 1])
        validi = np.array([self.stands[(int(x), int(y))].hasFreeSpot() for x, y in self.coords])

        if not validi.any():
            raise ValueError

        i = np.flatnonzero(validi)[np.argmin(dist[validi])]
        return self.stands[(int(self.coords[i, 0]), int(self.coords[i, 1]))].pos


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
        
        
    def insertUserInLoco(self, standLocation: tuple[int, int], user: User) -> None:
        
        self.stands[standLocation].insertUser(user)
        
        
    def insertUserOnLine(self, user: User) -> None:
        
        self.onlineQueue.append(user)
    
    
    def getUser(self, standLocation: tuple[int, int]) -> tuple[User, bool]:
        
        if len(self.onlineQueue) == 0:
            return self.stands[standLocation].getUser(), True
        
        if not self.stands[standLocation].hasWaitingUser():
            return self.onlineQueue.pop(0), False
        
        inLocoTime = self.stands[standLocation].getNextUserTime()
        if inLocoTime < self.onlineQueue[0].getArrivalToStandTime():
            return self.stands[standLocation].getUser(), True
        else:
            return self.onlineQueue.pop(0), False
    
    
    def existsIdleTaxi(self) -> bool:
        if self.totalIdleTaxi > 0:
            return True
        return False 
    
    
    def isIdle(self, standLocation: tuple[int, int]) -> bool:
        return self.stands[standLocation].hasIdleTaxi()
    
    
    def hasUserOnLine(self) -> bool:
        if len(self.onlineQueue) > 0: return True
        
        return False
    
    
    def getOnLineUser(self) -> User:
        
        return self.onlineQueue.pop(0)
    
    
    def hasFreeSpace(self, standLocation: tuple[int, int]) -> bool:
        
        return self.stands[standLocation].hasFreeSpot()
    
    
    def hasWaitingUser(self, standLocation: tuple[int, int]) -> bool:
        
        return len(self.onlineQueue) > 0 or self.stands[standLocation].hasWaitingUser()
    
    def __str__(self):
        return f"TaxiStands: {self.stands.values()}\nOnlineQueue: {self.onlineQueue}"
            