from User import User
import heapq

class Event():
    
    _counter = 0
    
    
    def __init__(self, eventType: str, time: int, location: tuple[int, int], user: User | None):
        
        self.eventType = eventType
        self.time = time
        self.coord = location
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
        return self.coord
    
    
    def getUser(self) -> User | None:
        return self.user
    
    def __str__(self):
        return f"{self.eventType} -- {self.time} -- {self.coord} -- {self.user}"
    
    def __repr__(self):
        return f"{self.eventType} -- time: {self.time} -- location: {self.coord} -- user: {self.user}"


class FutureEventSet:
    
    def __init__(self):
        self.queue = []
        
        
    def insertEvent(self, event: Event) -> None:
        
        heapq.heappush(self.queue, (event.sortKey(), event))
        
        
    def getEvent(self) -> Event:
        
        return heapq.heappop(self.queue)[-1]
    
    def __str__(self):
        return f"{self.queue}"