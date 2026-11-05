"""Rilevamento online della fine della warm-up (confronto tra finestre di batch means). Solo numpy."""

from collections import deque

import numpy as np


class WarmupDetector:
    """update(t, value) a ogni tick. stationary: None = in corso, True = rilevata, False = timeout.

    Medie di batch di `batch` tick; si tengono le ultime `window` medie. Se la media non sta
    crescendo (2a metà della finestra non più alta della 1a di più di z errori standard)
    per `patience` batch di fila, la warm-up è finita."""

    def __init__(self, batch=50, window=20, z=2.0, patience=5, min_t=500, max_t=50000):
        self.batch, self.window, self.z, self.patience = batch, window, z, patience
        self.min_t, self.max_t = min_t, max_t
        self.means = deque(maxlen=window)
        self.acc, self.n, self.streak = 0.0, 0, 0
        self.warmup_end = None
        self.stationary = None

    def update(self, t, value) -> bool:
        if self.stationary is not None:
            return self.stationary
        if t > self.max_t:                  # niente stazionarietà entro max_t
            self.stationary = False
            return False

        self.acc += value
        self.n += 1
        if self.n < self.batch:
            return False
        self.means.append(self.acc / self.n)
        self.acc, self.n = 0.0, 0

        if len(self.means) == self.window and t >= self.min_t:
            h = self.window // 2
            first, second = np.array(self.means)[:h], np.array(self.means)[h:]
            se = np.sqrt((first.var(ddof=1) + second.var(ddof=1)) / h)
            growing = second.mean() - first.mean() > self.z * se
            self.streak = 0 if growing else self.streak + 1
            if self.streak >= self.patience:
                self.warmup_end = t - self.window * self.batch    # inizio della finestra (conservativo)
                self.stationary = True
        return self.stationary is True


class MultiWarmupDetector:
    """Più detector insieme: warm-up finita solo quando lo sono tutti."""

    def __init__(self, detectors):
        self.detectors = list(detectors)

    def update(self, t, values) -> bool:
        done = [d.update(t, v) for d, v in zip(self.detectors, values)]
        return all(done)

    @property
    def stationary(self):
        if any(d.stationary is False for d in self.detectors):
            return False
        return True if all(d.stationary for d in self.detectors) else None

    @property
    def warmup_end(self):
        return max(d.warmup_end for d in self.detectors) if self.stationary else None
