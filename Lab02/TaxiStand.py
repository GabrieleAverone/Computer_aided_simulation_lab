
import numpy as np
from User import User

"""
    
    TO-DO:
        La coda onlineQueue è da mettere dentro TaxiStands perché è una coda condivisa con tutti gli stand di Taxi
        
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
        
    
    
class TaxiStands():
    
    def __init__(self, capacity, pos: tuple[tuple[int, int], ...]):
        
        if len(pos) != len(capacity):
            raise ValueError("The vector pos and capacity must be the same size")
        
        self.nStands = len(capacity)
        self.stands: dict[int, TaxiStand] = {}

        for i in range(len(capacity)):
            self.stands[i] =  TaxiStand(pos[i][0], pos[i][1], capacity[i])
            
        self.coord = np.array(pos)
        

    def findNearestTaxiStand(self, x, y) -> int:
            
        taxiPos = np.array(x, y)
        
        dist = abs(taxiPos[0] - self.coord[:,0]) + abs(taxiPos[1] - self.coord[:,1]) 
        minStandId = np.argmin(dist)

        return int(minStandId)
    
    
    def taxiArrival(self, standID: int) -> bool:
        
        if self.stands[standID].hasFreeSpot():
            
            self.stands[standID].insertTaxi()
            return True
        
        else:
            return False
        
    
    def taxiDeparture(self, standID: int) -> bool:
        
        if self.stands[standID].hasIdleTaxi():
            self.stands[standID].getTaxi()
            return True

        else:
            return False
        
        
    def insertUser(self, standID: int, user: User, inLoco: bool):

        self.stands[standID].insertUser(user, inLoco)
        
    
    def getUser(self, standID: int) -> User:
        
        user, inLoco = self.stands[standID].getUser()
        
        if not inLoco:
            for i in range(self.nStands):
                if i != standID:
                    self.stands[i].updateDiscardOnline()
                    
        
        return user
        