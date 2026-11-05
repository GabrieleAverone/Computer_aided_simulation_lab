
class User:

    _counter = 0


    def __init__(self, spawnTime: int, spawnLocation: tuple[int, int], destination: tuple[int, int], inLoco: bool) -> None:

        self.spawnTime = spawnTime
        self.spawnLocation = spawnLocation
        self.destination = destination
        self.inLocoFlag = inLoco
        self.nextLocation = None
        self.arrivalToStandTime = None
        self.callTaxiTime = None

        self.counter = User._counter
        User._counter += 1


    def getArrivalToStandTime(self) -> int:

        if self.arrivalToStandTime is not None:
            return self.arrivalToStandTime

        else:
            raise ValueError("The field arrivalToStandTime is not defined")


    def getInLocoFlag(self) -> bool:
        return self.inLocoFlag


    def getSpawnLocation(self) -> tuple[int, int]:
        return self.spawnLocation


    def setNextLocation(self, location: tuple[int, int]) -> None:
        self.nextLocation = location


    def getDestination(self) -> tuple[int, int]:
        return self.destination


    def setArrivalToStandTime(self, time: int) -> None:
        self.arrivalToStandTime = time


    def setCallTaxiTime(self, time: int) -> None:
        self.callTaxiTime = time


    def getTaxiCallTime(self) -> int:
        if self.callTaxiTime is not None:
            return self.callTaxiTime
        else:
            raise ValueError("The field callTaxiTime is not defined")


    def __str__(self):
        return f"{self.counter}"

    def __repr__(self):
        return f"{self.counter}"
