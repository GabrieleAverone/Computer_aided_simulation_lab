from Events import Event
import heapq


class FutureEventSet:

    def __init__(self):
        self.queue = []


    def insertEvent(self, event: Event) -> None:

        heapq.heappush(self.queue, (event.sortKey(), event))


    def getEvent(self) -> Event:

        return heapq.heappop(self.queue)[-1]
