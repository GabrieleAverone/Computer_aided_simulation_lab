
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
            return self.userQueue.pop()
        else:
            raise ValueError
        
    
    def insertUser(self, user: User) -> None:
        
        self.userQueue.append(user)
        
        
    def getNextUserTime(self) -> int:
        
        return self.userQueue[0].getArrivalToStandTime()
            
            
    def updateDiscardOnline(self):
        self.discardOnlineUser += 1
        
        
    def getCapacity(self) -> int:
        return self.capacity
    
    
    def assignTaxis(self, nTaxi: int) -> None:
        self.nTaxi += nTaxi
        
    
    
class TaxiStands():
    
    def __init__(self, capacity, pos: Sequence[tuple[int, int]]):
        
        if len(pos) != len(capacity):
            raise ValueError("The vector pos and capacity must be the same size")
        
        self.nStands = len(capacity)
        self.stands: dict[tuple[int, int], TaxiStand] = {}

        for i in range(self.nStands):
            self.stands[pos[i]] =  TaxiStand(pos[i], capacity[i])
            
        self.coords = np.array(pos)
        
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
            
            for i in range(self.nStands):
                if self.stands[self.coords[i]].getCapacity() <= taxiPerStand:
                    self.stands[self.coords[i]].assignTaxis(taxiPerStand)
                    remaining -= taxiPerStand
                else:
                    self.stands[self.coords[i]].assignTaxis(self.stands[self.coords[i]].getCapacity())
                    remaining -= self.stands[self.coords[i]].getCapacity()
            
            while remaining > 0:
                for i in range(self.nStands):
                    if self.stands[self.coords[i]].hasFreeSpot():
                        self.stands[self.coords[i]].assignTaxis(1)
                        remaining -= 1
                        
        else: raise ValueError("Policy non recognised")
                    

    def findNearestTaxiStand(self, coord: tuple[int, int]) -> tuple[int, int]:
        taxiPos = np.array(coord, dtype=int)

        dist = abs(taxiPos[0] - self.coords[:, 0]) + abs(taxiPos[1] - self.coords[:, 1])
        minIndex = int(np.argmin(dist))
        minDistCoord = (int(self.coords[minIndex, 0]), int(self.coords[minIndex, 1]))

        return self.stands[minDistCoord].pos
    
    
    def taxiCall(self, coord: tuple[int, int]) -> tuple[int, int]:
        pos = np.array(coord, dtype=int)

        dist = np.abs(pos[0] - self.coords[:, 0]) + np.abs(pos[1] - self.coords[:, 1])
        validi = np.array([self.stands[(int(x), int(y))].hasIdleTaxi() for x, y in self.coords])

        if not validi.any():
            raise ValueError("Nessun parcheggio con taxi liberi")

        i = np.flatnonzero(validi)[np.argmin(dist[validi])]
        return self.stands[(int(self.coords[i, 0]), int(self.coords[i, 1]))].pos
                
                
    def taxiArrival(self, standLocation: tuple[int, int]) -> bool:
        
        if self.stands[standLocation].hasFreeSpot():
            
            self.stands[standLocation].insertTaxi()
            self.totalIdleTaxi += 1
            return True
        
        else:
            return False
        
    
    def taxiDeparture(self, standLocation: tuple[int, int]) -> bool:
        
        if self.stands[standLocation].hasIdleTaxi():
            self.totalIdleTaxi -= 1
            self.stands[standLocation].getTaxi()
            return True

        else:
            return False
        
        
    def insertUserInLoco(self, standLocation: tuple[int, int], user: User) -> None:
        
        self.stands[standLocation].insertUser(user)
        
        
    def insertUserOnLine(self, user: User) -> None:
        
        self.onlineQueue.append(user)
    
    
    def getUser(self, standLocation: tuple[int, int]) -> tuple[User, bool]:
        
        inLocoTime = self.stands[standLocation].getNextUserTime()
        
        if inLocoTime <= self.onlineQueue[0].getArrivalToStandTime():
            return self.stands[standLocation].getUser(), True
        
        else:
            return self.onlineQueue.pop(), False
    
    
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
        
        return self.onlineQueue.pop()
    
    
    def hasFreeSpace(self, standLocation: tuple[int, int]) -> bool:
        
        return self.stands[standLocation].hasFreeSpot()
    
    
    def hasWaitingUser(self, standLocation: tuple[int, int]) -> bool:
        
        return len(self.onlineQueue) > 0 or self.stands[standLocation].hasWaitingUser()
            