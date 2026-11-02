from Events import Event
import heapq


class FutureEventSet:

    def __init__(self):
        self.queue = []


    def insertEvent(self, event: Event) -> None:

        heapq.heappush(self.queue, (event.sortKey(), event))


    def getEvent(self) -> Event:

        return heapq.heappop(self.queue)[-1]


    def __str__(self):
        # one event per line, in chronological order (the heap itself is not sorted)
        if not self.queue:
            return "    (empty)"
        sortedItems = sorted(self.queue, key=lambda item: item[0])
        return "\n".join(f"    {event!r}" for _, event in sortedItems)
