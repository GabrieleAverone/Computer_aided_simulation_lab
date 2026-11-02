

class User:
    
    _counter = 0
    
    def __init__(self, spawnTime: int, spawnPos: tuple[int, int], destPos: tuple[int, int], inLoco: bool) -> None:
        
        self.spawTime = spawnTime
        self.spawnPos = spawnPos
        self.destPos = destPos
        self.inLocoFlag = inLoco
        self.arrivalTimeToStand = None
        self.callTaxiTime = None
        
        self.counter = User._counter
        User._counter += 1
        
        
    def getArrivalToStandTime(self) -> int:
        
        if self.arrivalTimeToStand is not None:
            return self.arrivalTimeToStand
        
        else:
            raise ValueError("The field arrivalToStand is not definied")
        
        
    def getInLocoFlag(self) -> bool:
        return self.inLocoFlag
    
    
    def getSPawnLocation(self) -> tuple[int, int]:
        return self.spawnPos
    
            
    def setNextLocation(self, coord: tuple[int, int]) -> None:
        self.nextPos = coord
    
    
    def getDestination(self) -> tuple[int, int]:
        return self.destPos
    
    def setArrivalToStandTime(self, time: int) -> None:
        self.arrivalTimeToStand = time
        
    def setCallTaxiTime(self, time: int) -> None:
        self.callTaxiTime = time
        
    def getTaxiCallTime(self) -> int:
        if self.callTaxiTime is not None:
            return self.callTaxiTime
        else:
            raise ValueError
    
    def __str__(self):
        return f"{self.counter}"
    
    def __repr__(self):
        return f"{self.counter}"
    