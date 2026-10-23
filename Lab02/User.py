

class User:
    
    def __init__(self, spawnTime: int, spawnPos: tuple[int, int], destPos: tuple[int, int], inLoco: bool) -> None:
        
        self.spawTime = spawnTime
        self.spawnPos = spawnPos
        self.destPos = destPos
        self.nextPos = None
        self.inLoco = inLoco
        self.arrivalToStand = None
        
        
    def getArrivalTime(self) -> int:
        
        if self.arrivalToStand is not None:
            return self.arrivalToStand
        
        else:
            raise ValueError("The field arrivalToStand is not definied")
        
        
    def getInLocoFlag(self) -> bool:
        return self.inLoco
    
    
    def getSPawnLocation(self) -> tuple[int, int]:
        return self.spawnPos
    
            
    def setNextLocation(self, coord: tuple[int, int]) -> None:
        self.nextPos = coord
        
    def getNextLocation(self) -> tuple[int, int]:
        if self.nextPos is None:
            raise ValueError("QUalcosa non funziona")
        
        return self.nextPos
    
    
    def getDestination(self) -> tuple[int, int]:
        return self.destPos
    