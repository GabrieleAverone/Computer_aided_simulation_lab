"""Rilevamento online della fine della warm-up (confronto tra finestre di batch means). Solo numpy."""

from collections import deque

import numpy as np


class WarmupDetector:
    """update(t, value) a ogni tick. stationary: None = in corso, True = rilevata, False = timeout."""

    def __init__(self, batch=50, k=10, eps=0.05, patience=5, min_t=500, abs_tol=0.5, max_t=50000):
        self.batch, self.k, self.eps, self.patience = batch, k, eps, patience
        self.min_t, self.abs_tol, self.max_t = min_t, abs_tol, max_t
        self.means = deque(maxlen=2 * k)    # ultimi 2k batch means
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

        if len(self.means) == 2 * self.k and t >= self.min_t:
            m = np.array(self.means)
            meanA, meanB = m[:self.k].mean(), m[self.k:].mean()
            scale = max(abs(meanA), self.abs_tol)
            slope = np.polyfit(np.arange(2 * self.k), m, 1)[0]
            ok = abs(meanB - meanA) / scale < self.eps and abs(slope * 2 * self.k) / scale < self.eps
            self.streak = self.streak + 1 if ok else 0
            if self.streak >= self.patience:
                self.warmup_end = t - 2 * self.k * self.batch    # inizio finestra A (conservativo)
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
