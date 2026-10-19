
import numpy as np
from User import User
from helpers import manhattan_distance

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
    
    
    def getUser(self) -> User:
        
        if len(self.onLineQueue) == 0:
            return self.inLocoQueue.pop()
        
        elif len(self.inLocoQueue) == 0:
            
            for i in range(self.discardOnlineUser):
                self.onLineQueue.pop()
                
            return self.onLineQueue.pop()
        
        elif self.inLocoQueue[0].getArrivalTime() >= self.onLineQueue[0].getArrivalTime():
            return self.inLocoQueue.pop()
        
        else: 
            for i in range(self.discardOnlineUser):
                self.onLineQueue.pop()
                            
            return self.onLineQueue.pop()
        
    
    def insertUser(self, user: User, inLoco: bool) -> None:
        
        if inLoco:
            self.inLocoQueue.append(user)
        else:
            self.onLineQueue.append(user)
        
    
    
class TaxiStands():
    
    def __init__(self, capacity, pos):
        
        if len(pos) != len(capacity):
            raise ValueError("The vector pos and capacity must be the same size")
        
        self.stands: dict[int, TaxiStand] = {}

        for i in range(len(capacity)):
            self.stands[i] =  TaxiStand(pos[i][0], pos[i][1], capacity[i])
        
    
    def findNearestTaxiStand(self, x, y) -> int:
        
        dists = []
        
        for stand in self.stands:
            
            dist = 
        
        
        
        
    
    