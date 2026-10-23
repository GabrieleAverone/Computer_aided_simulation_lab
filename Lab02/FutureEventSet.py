from User import User
import heapq

class Event():
    
    _counter = 0
    
    
    def __init__(self, eventType: str, time: int, user: User | None):
        
        self.eventType = eventType
        self.time = time
        self.counter = self._counter
        self._counter += 1
        self.user = user
        
        
    def sortKey(self) -> tuple[int, int]:
        
        return self.time, self.counter
    
    
    def getTime(self) -> int:
        return self.time
    
    
    def getType(self) -> str:
        return self.eventType
    
    
    def getUser(self) -> User | None:
        return self.user



class FutureEventSet:
    
    def __init__(self):
        self.queue = []
        
        
    def insertEvent(self, event: Event) -> None:
        
        heapq.heappush(self.queue, (event.sortKey(), event))
        
        
    def getEvent(self) -> Event:
        
        return heapq.heappop(self.queue)[-1]