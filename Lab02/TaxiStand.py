
import numpy as np
from collections.abc import Sequence
from User import User

"""
    
    TO-DO:
        - Togliere gli id numerici da stands e usare le coordinate dellos tand come ID
        - Controllare contatori vari
        - La coda onlineQueue è da mettere dentro TaxiStands perché è una coda condivisa con tutti gli stand di Taxi
        - Implementare lal ricerca dello stand più vicino in maniera più efficiente ->
                dividere la superficie della città in sezioni, ogni sezione assegnata a un taxiStand
        
"""

class TaxiStand:
    
    def __init__(self, x: int, y: int, capacity: int):
        
        self.x = x
        self.y = y
        self.capacity = capacity
        self.nTaxi = 0
        self.inLocoQueue: list[User] = []
        self.onLineQueue: list[User] = [] 
        self.discardOnlineUser = 0
        
        
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
        
        if len(self.inLocoQueue) > 0 or len(self.onLineQueue) > 0: return True
        else: return False
    
    
    def getUser(self) -> tuple[User, bool]:
        
        if len(self.onLineQueue) == 0:
            return self.inLocoQueue.pop(), True
        
        elif len(self.inLocoQueue) == 0:
            
            for i in range(self.discardOnlineUser):
                self.onLineQueue.pop()
            
            self.discarOnliceUser = 0
            return self.onLineQueue.pop(), False
        
        elif self.inLocoQueue[0].getArrivalTime() >= self.onLineQueue[0].getArrivalTime():
            return self.inLocoQueue.pop(), True
        
        else: 
            for i in range(self.discardOnlineUser):
                self.onLineQueue.pop()
            
            self.discarOnliceUser = 0                
            return self.onLineQueue.pop(), False
        
    
    def insertUser(self, user: User, inLoco: bool) -> None:
        
        if inLoco:
            self.inLocoQueue.append(user)
        else:
            self.onLineQueue.append(user)
            
            
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
        self.stands: dict[int, TaxiStand] = {}

        for i in range(self.nStands):
            self.stands[i] =  TaxiStand(pos[i][0], pos[i][1], capacity[i])
            
        self.coord = np.array(pos)
        
        self.totalCapacity = 0
        for cap in capacity:
            self.totalCapacity += cap
            
        self.totalIdleTaxi = 0
        self.waitingOnLine = 0
        
    
    def distributeTaxi(self, nTaxi: int, policy: str) -> None:
        
        self.totalIdleTaxi = nTaxi
        if nTaxi > self.totalCapacity:
            raise ValueError("# of taxi > Total capacity")
        
        if policy == "uniform":
            remaining = nTaxi
            taxiPerStand = nTaxi // self.nStands
            
            for i in range(self.nStands):
                if self.stands[i].getCapacity() <= taxiPerStand:
                    self.stands[i].assignTaxis(taxiPerStand)
                    remaining -= taxiPerStand
                else:
                    self.stands[i].assignTaxis(self.stands[i].getCapacity())
                    remaining -= self.stands[i].getCapacity()
            
            while remaining > 0:
                for i in range(self.nStands):
                    if self.stands[i].hasFreeSpot():
                        self.stands[i].assignTaxis(1)
                        remaining -= 1
                        
        else: raise ValueError("Policy non recognised")
                    

    def findNearestTaxiStand(self, coord: tuple[int, int]) -> tuple[int, int]:
            
        taxiPos = np.array(coord, dtype=int)
        
        dist = abs(taxiPos[0] - self.coord[:,0]) + abs(taxiPos[1] - self.coord[:,1]) 
        minStandId = int(np.argmin(dist))

        return self.stands[minStandId].x, self.stands[minStandId].y
    
    
    def taxiCall(self, coord: tuple[int, int]) -> tuple[int, int]:
        pos = np.array(coord, dtype=int)
        
    
        dist = abs(pos[0] - self.coord[:,0]) + abs(pos[1] - self.coord[:,1])
        validi = np.array([self.stands[i].hasIdleTaxi() for i in range(self.nStands)])
        # oppure vettorizzata, es: validi = capacita > 0

        if not validi.any():
            raise ValueError("Something is not working")
        return self.stands[np.flatnonzero(validi)[np.argmin(dist[validi])]].x, self.stands[np.flatnonzero(validi)[np.argmin(dist[validi])]].y
                
                
    def taxiArrival(self, standID: int) -> bool:
        
        if self.stands[standID].hasFreeSpot():
            
            self.stands[standID].insertTaxi()
            self.totalIdleTaxi += 1
            return True
        
        else:
            return False
        
    
    def taxiDeparture(self, standID: int) -> bool:
        
        if self.stands[standID].hasIdleTaxi():
            self.totalIdleTaxi -= 1
            self.stands[standID].getTaxi()
            return True

        else:
            return False
        
        
    def insertUserInLoco(self, standID: int, user: User) -> None:
        
        self.stands[standID].insertUser(user, inLoco=True)
        
        
    def insertUserOnLine(self, user: User) -> None:
        
        self.waitingOnLine += 1
        
        for i in range(self.nStands):
            self.stands[i].insertUser(user, inLoco=False)
    
    
    def getUser(self, standID: int) -> User:
        
        user, inLoco = self.stands[standID].getUser()
        
        if not inLoco:
            self.waitingOnLine -= 1
            for i in range(self.nStands):
                if i != standID:
                    self.stands[i].updateDiscardOnline()
                    
        
        return user
    
    
    def existsIdleTaxi(self) -> bool:
        if self.totalIdleTaxi > 0:
            return True
        return False 
    
    
    def getStandID(self, coord: tuple[int, int]) -> int:
        
        raise NotImplementedError()
    
    
    def isIdle(self, ID: int) -> bool:
        return self.stands[ID].hasIdleTaxi()
    
    
    def hasUserOnLine(self) -> bool:
        if self.waitingOnLine > 0: return True
        
        return False
    
    
    def getOnLineUser(self) -> User:
        
        raise NotImplementedError
            