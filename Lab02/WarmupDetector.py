class WarmupDetector:
    """
    Detector del warm-up in tempo reale (per ora: solo le statistiche per finestra).

    Lo stato della simulazione è costante tra un evento e il successivo, quindi la
    media di una finestra è calcolata PESATA SUL TEMPO:

        m_k = sum(valore_i * durata_i) / sum(durata_i)

    La finestra k è formata da `windowSize` eventi consecutivi, senza sovrapposizione
    con la finestra k-1. Si tiene una media per ciascuna variabile monitorata.

    Fine del warm-up: dalla finestra k (con almeno t finestre precedenti) si calcola, per ogni variabile,

        ref_k = media di m_{k-t}, ..., m_{k-1}
        stabile  se  |m_k - ref_k| / max(ref_k, delta) < eps          (tolleranza relativa)

    oppure, se si passa absTol, con tolleranza ASSOLUTA (in clienti, eps e delta si ignorano):

        stabile  se  |m_k - ref_k| < absTol

    La finestra k è "stabile" se lo sono TUTTE le variabili. Il warm-up è finito quando si hanno
    `confirm` finestre stabili consecutive: il detector lo segnala (warmupDone, detectionTime,
    detectionWindow) e da lì non controlla più.

    Uso (stessa posizione di Metrics.update, cioè a ogni evento PRIMA di processarlo):

        detector = WarmupDetector(windowSize=500)
        ...
        detector.update(time, {"queueInLoco": totInLoco, "queueOnLine": totOnLine})
        detector.windowMeans["queueInLoco"]      # [m_0, m_1, ...] finestre completate
    """

    def __init__(self, windowSize: int, variables: tuple[str, ...] = ("queueInLoco", "queueOnLine", "queueTotal"),
                 t: int = 5, eps: float = 0.05, delta: float = 1.0, confirm: int = 2,
                 absTol: float | None = None) -> None:
        if windowSize < 1 or t < 1 or confirm < 1:
            raise ValueError("windowSize, t e confirm devono essere >= 1")
        if eps <= 0 or delta <= 0 or (absTol is not None and absTol <= 0):
            raise ValueError("eps, delta e absTol devono essere > 0")
        self.absTol = absTol
        self.windowSize = windowSize
        self.t = t
        self.eps = eps
        self.delta = delta
        self.confirm = confirm

        # esito del rilevamento
        self.warmupDone = False
        self.detectionTime: int | None = None       # tempo di simulazione in cui è stato segnalato
        self.detectionWindow: int | None = None     # indice della finestra che ha confermato
        self.windowEndTimes: list[int] = []
        self._stableStreak = 0
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
        self.windowEndTimes.append(time)
        self._resetWindow()

        if not self.warmupDone:
            self._checkWarmupEnd(time)
        return True


    def _isStable(self, k: int) -> bool:
        """La finestra k è stabile rispetto alle t precedenti, per tutte le variabili."""
        if k < self.t:
            return False
        for v in self.variables:
            means = self.windowMeans[v]
            ref = sum(means[k - self.t:k]) / self.t
            diff = abs(means[k] - ref)
            if self.absTol is not None:
                if diff >= self.absTol:
                    return False
            elif diff / max(ref, self.delta) >= self.eps:
                return False
        return True


    def _checkWarmupEnd(self, time: int) -> None:
        k = self.nWindows - 1
        self._stableStreak = self._stableStreak + 1 if self._isStable(k) else 0
        if self._stableStreak >= self.confirm:
            self.warmupDone = True
            self.detectionTime = time
            self.detectionWindow = k
