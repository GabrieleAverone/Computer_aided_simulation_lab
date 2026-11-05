# quantile t di Student (bilaterale, 95%) per gradi di libertà 1..30; oltre 30 si usa 1.96
_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def linearSlope(y: list[float]) -> tuple[float, float]:
    """Regressione lineare di y contro 0, 1, ..., n-1 (n >= 3).
    Restituisce (pendenza, errore standard della pendenza)."""
    n = len(y)
    xm = (n - 1) / 2
    ym = sum(y) / n
    sxx = sum((i - xm) ** 2 for i in range(n))
    slope = sum((i - xm) * (v - ym) for i, v in enumerate(y)) / sxx
    sse = sum((v - ym - slope * (i - xm)) ** 2 for i, v in enumerate(y))
    return slope, (sse / (n - 2) / sxx) ** 0.5


class WarmupDetector:
    """
    Detector del warm-up in tempo reale (per ora: solo le statistiche per finestra).

    Lo stato della simulazione è costante tra un evento e il successivo, quindi la
    media di una finestra è calcolata PESATA SUL TEMPO:

        m_k = sum(valore_i * durata_i) / sum(durata_i)

    La finestra k è formata da `windowSize` eventi consecutivi, senza sovrapposizione
    con la finestra k-1. Si tiene una media per ciascuna variabile monitorata.

    Fine del warm-up: dalla finestra k (con almeno t finestre precedenti) si applicano, per ogni variabile,
    due test, che devono valere entrambi:

    TEST SULLA MEDIA:

        ref_k = media di m_{k-t}, ..., m_{k-1}
        stabile  se  |m_k - ref_k| / max(ref_k, delta) < eps

    TEST SULLA PENDENZA: regressione lineare delle t+1 medie m_{k-t}, ..., m_k contro il numero di finestra;
    la pendenza non deve essere distinguibile da zero:

        stabile  se  |pendenza| <= c * SE(pendenza)

    con SE dai residui della regressione e c il quantile t di Student al 95% (con t+1-2 gradi di libertà).
    Il rumore entra nel criterio: la soglia si adatta da sola.

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
                 t: int = 5, eps: float = 0.05, delta: float = 1.0, confirm: int = 2) -> None:
        if windowSize < 1 or t < 1 or confirm < 1:
            raise ValueError("windowSize, t e confirm devono essere >= 1")
        if eps <= 0 or delta <= 0:
            raise ValueError("eps e delta devono essere > 0")
        if t < 2:
            raise ValueError("il test sulla pendenza richiede t >= 2")
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
            if not (self._meanStable(means, k) and self._slopeStable(means, k)):
                return False
        return True


    def _meanStable(self, means: list[float], k: int) -> bool:
        ref = sum(means[k - self.t:k]) / self.t
        diff = abs(means[k] - ref)
        return diff / max(ref, self.delta) < self.eps


    def _slopeStable(self, means: list[float], k: int) -> bool:
        slope, se = linearSlope(means[k - self.t:k + 1])
        dof = self.t - 1                                    # (t+1) punti - 2
        crit = _T95[dof - 1] if dof <= len(_T95) else 1.96
        return abs(slope) <= crit * se


    def _checkWarmupEnd(self, time: int) -> None:
        k = self.nWindows - 1
        self._stableStreak = self._stableStreak + 1 if self._isStable(k) else 0
        if self._stableStreak >= self.confirm:
            self.warmupDone = True
            self.detectionTime = time
            self.detectionWindow = k
