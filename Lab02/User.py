

class User:
    
    def __init__(self, spawnTime: int, spawnPos: tuple[int, int], destPos: tuple[int, int], inLoco: bool) -> None:
        
        self.spawTime = spawnTime
        self.spawnPos = spawnPos
        self.destPos = destPos
        self.inLoco = inLoco
        self.arrivalToStand = None
        
        
    def getArrivalTime(self) -> int:
        
        if self.arrivalToStand is not None:
            return self.arrivalToStand
        
        else:
            raise ValueError("The field arrivalToStand is not definied")