from User import User


class Event():

    _counter = 0


    def __init__(self, eventType: str, time: int, location: tuple[int, int], user: User | None):

        self.eventType = eventType
        self.time = time
        self.location = location
        self.counter = Event._counter
        Event._counter += 1
        self.user = user


    def sortKey(self) -> tuple[int, int]:
        return self.time, self.counter


    def getType(self) -> str:
        return self.eventType


    def getTime(self) -> int:
        return self.time


    def getLocation(self) -> tuple[int, int]:
        return self.location


    def getUser(self) -> User | None:
        return self.user


    def __str__(self):
        return f"#{self.counter} {self.eventType} -- {self.time} -- {self.location} -- {self.user}"

    def __repr__(self):
        return f"#{self.counter} {self.eventType} -- time: {self.time} -- location: {self.location} -- user: {self.user}"
