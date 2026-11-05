class WarmupDetector:
    """
    Detector del warm-up in tempo reale (per ora: solo le statistiche per finestra).

    Lo stato della simulazione è costante tra un evento e il successivo, quindi la
    media di una finestra è calcolata PESATA SUL TEMPO:

        m_k = sum(valore_i * durata_i) / sum(durata_i)

    La finestra k è formata da `windowSize` eventi consecutivi, senza sovrapposizione
    con la finestra k-1. Si tiene una media per ciascuna variabile monitorata.

    Uso (stessa posizione di Metrics.update, cioè a ogni evento PRIMA di processarlo):

        detector = WarmupDetector(windowSize=500)
        ...
        detector.update(time, {"queueInLoco": totInLoco, "queueOnLine": totOnLine})
        detector.windowMeans["queueInLoco"]      # [m_0, m_1, ...] finestre completate
    """

    def __init__(self, windowSize: int, variables: tuple[str, ...] = ("queueInLoco", "queueOnLine")) -> None:
        if windowSize < 1:
            raise ValueError("windowSize deve essere >= 1")
        self.windowSize = windowSize
        self.variables = tuple(variables)

        # medie delle finestre completate, una lista per variabile
        self.windowMeans: dict[str, list[float]] = {v: [] for v in self.variables}

        self.lastTime = 0
        self._resetWindow()


    def _resetWindow(self) -> None:
        self._nEvents = 0
        self._duration = 0
        self._weightedSum = {v: 0 for v in self.variables}
        self._lastValues = {v: 0 for v in self.variables}


    @property
    def nWindows(self) -> int:
        """Numero di finestre completate."""
        return len(self.windowMeans[self.variables[0]])


    def update(self, time: int, state: dict[str, float]) -> bool:
        """Registra un evento. `state` è lo stato PRIMA dell'evento, valido in [lastTime, time].
        Restituisce True se con questo evento si è chiusa una finestra."""
        dt = time - self.lastTime
        self.lastTime = time

        for v in self.variables:
            value = state[v]
            self._weightedSum[v] += value * dt
            self._lastValues[v] = value
        self._duration += dt
        self._nEvents += 1

        if self._nEvents < self.windowSize:
            return False

        for v in self.variables:
            # finestra di durata nulla (eventi tutti allo stesso istante): vale l'ultimo valore
            mean = self._weightedSum[v] / self._duration if self._duration > 0 else self._lastValues[v]
            self.windowMeans[v].append(mean)
        self._resetWindow()
        return True
