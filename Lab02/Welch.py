"""
Metodo di Welch e controllo di stabilità (trend nella seconda metà della run).

Solo numpy: non dipende dalla simulazione. Gli input sono, per ogni replica, le
serie a tratti costanti registrate da Metrics.stateSeries():
    {"ends": [t1, t2, ...], "idleTaxi": [...], "queueInLoco": [...], "queueOnLine": [...]}
dove il valore k-esimo vale nell'intervallo [ends[k-1], ends[k]) (con ends[-1] = 0).

Passi:
  1. binStateSeries / buildMatrices : medie pesate nel tempo su intervalli di ampiezza delta
        Y[j, i] = (1/delta) * integrale di Q_j(t) su [(i-1)*delta, i*delta)
  2. verticalMean                   : Ybar[i] = media di Y[j, i] sulle repliche
  3. welchMovingAverage             : media mobile centrata con finestra 2w+1
  4. blockCheck                     : nella seconda metà della run la media cresce blocco dopo blocco?
"""

import numpy as np

METRICS = ("idleTaxi", "queueInLoco", "queueOnLine")
QUEUE_METRICS = ("queueInLoco", "queueOnLine")      # idleTaxi escluso dal test di stabilità



# ------------------------------------------------------------------
# 1. Discretizzazione su griglia comune
# ------------------------------------------------------------------
def cumulativeIntegral(series: dict, key: str, times) -> np.ndarray:
    """Integrale da 0 a t della serie costante a tratti, calcolato in modo esatto
    agli istanti `times` (l'integrale è lineare tra due eventi: basta interpolare)."""
    ends = np.concatenate(([0.0], np.asarray(series["ends"], dtype=float)))
    values = np.asarray(series[key], dtype=float)
    F = np.concatenate(([0.0], np.cumsum(values * np.diff(ends))))
    return np.interp(times, ends, F)


def binStateSeries(series: dict, key: str, maxTime: int, delta: int) -> np.ndarray:
    """Riga di Y per una replica: media pesata nel tempo su ogni intervallo di ampiezza delta.
    Gli istanti degli eventi sono diversi da replica a replica, quindi si lavora sul tempo,
    mai sull'indice dell'evento. Gli ultimi maxTime % delta passi (intervallo incompleto) si scartano."""
    m = maxTime // delta
    edges = np.arange(m + 1) * float(delta)
    return np.diff(cumulativeIntegral(series, key, edges)) / delta


def buildMatrices(allSeries: list[dict], maxTime: int, delta: int) -> dict[str, np.ndarray]:
    """Per ogni metrica la matrice Y (n repliche x m intervalli)."""
    return {key: np.array([binStateSeries(s, key, maxTime, delta) for s in allSeries])
            for key in METRICS}


# ------------------------------------------------------------------
# 2-3. Media verticale e media mobile di Welch
# ------------------------------------------------------------------
def verticalMean(Y: np.ndarray) -> np.ndarray:
    return Y.mean(axis=0)


def welchMovingAverage(ybar: np.ndarray, w: int) -> np.ndarray:
    """Media mobile centrata di Welch. Restituisce m - w valori (indici 1-based i = 1..m-w):
      - i = w+1 .. m-w : media di Ybar[i-w .. i+w]          (2w+1 punti)
      - i = 1 .. w     : media di Ybar[1 .. 2i-1]           (finestra simmetrica ridotta)
    Per i > m-w non è definita (mancano punti a destra)."""
    m = len(ybar)
    if w < 0 or w > m / 4:
        raise ValueError(f"serve 0 <= w <= m/4 (w={w}, m={m})")
    cs = np.concatenate(([0.0], np.cumsum(ybar)))      # cs[k] = somma dei primi k valori
    out = np.empty(m - w)
    for i in range(1, w + 1):
        out[i - 1] = (cs[2 * i - 1] - cs[0]) / (2 * i - 1)
    i = np.arange(w + 1, m - w + 1)
    out[w:] = (cs[i + w] - cs[i - w - 1]) / (2 * w + 1)
    return out


def intervalCenters(m: int, delta: int) -> np.ndarray:
    """Ascissa (in passi di simulazione) del centro di ogni intervallo."""
    return (np.arange(m) + 0.5) * delta


# ------------------------------------------------------------------
# 4. Controllo di stabilità
# ------------------------------------------------------------------
def blockCheckRow(y: np.ndarray, delta: int, maxTime: int, nBlocks: int = 4,
                  relTol: float = 0.25, absTol: float = 2.0) -> dict:
    """Controllo di stabilità su UNA serie (una riga di Y): nella seconda metà cresce blocco dopo blocco?
    Si prende la seconda metà della run (ascissa > maxTime/2), la si divide in nBlocks blocchi
    consecutivi e si calcola la media in ogni blocco.
    `unstable` se le medie dei blocchi crescono sempre e l'aumento totale (ultimo - primo) supera
    max(relTol * livello medio, absTol). absTol è in clienti: una coda instabile cresce di centinaia,
    una stabile oscilla di poche unità."""
    x = intervalCenters(len(y), delta)
    y2 = y[x > maxTime / 2]
    size = len(y2) // nBlocks
    blocks = y2[:size * nBlocks].reshape(nBlocks, size).mean(axis=1)
    level = float(blocks.mean())
    rise = float(blocks[-1] - blocks[0])
    increasing = bool(np.all(np.diff(blocks) > 0))
    return {"blocks": blocks, "level": level, "rise": rise, "increasing": increasing,
            "unstable": bool(increasing and rise > max(relTol * abs(level), absTol))}


def blockCheck(Y: np.ndarray, delta: int, maxTime: int, **thr) -> dict:
    """Come blockCheckRow, ma sulla media verticale delle repliche (usato per i grafici di Welch)."""
    return blockCheckRow(verticalMean(Y), delta, maxTime, **thr)


def idleSaturated(y: np.ndarray, delta: int, maxTime: int, nTaxi: int, idleTol: float = 0.01) -> bool:
    """Conferma da idleTaxi: True se nella seconda metà della run la frazione media di taxi liberi
    (idleTaxi / nTaxi) è sotto idleTol, cioè i taxi sono praticamente sempre occupati (ρ ≈ 1 o oltre)."""
    x = intervalCenters(len(y), delta)
    return bool(y[x > maxTime / 2].mean() / nTaxi < idleTol)


def stabilityPerReplica(Y: dict, delta: int, maxTime: int, nTaxi: int | None = None,
                        idleTol: float = 0.01, **thr) -> dict:
    """Per ogni replica: instabile se ALMENO UNA coda cresce, oppure (se nTaxi è noto) se nella seconda
    metà i taxi liberi sono in media meno di idleTol * nTaxi (idleSaturated). Poi riassunto sulla
    configurazione: pUnstable = frazione di repliche instabili; label = stabile (0), instabile (1)
    o metastabile (in mezzo)."""
    n = Y[QUEUE_METRICS[0]].shape[0]
    unstableRep = np.array([
        any(blockCheckRow(Y[k][j], delta, maxTime, **thr)["unstable"] for k in QUEUE_METRICS)
        or (nTaxi is not None and idleSaturated(Y["idleTaxi"][j], delta, maxTime, nTaxi, idleTol))
        for j in range(n)])
    p = float(unstableRep.mean())
    label = "stabile" if p == 0 else ("instabile" if p == 1 else "metastabile")
    return {"unstableReplicas": unstableRep, "pUnstable": p, "label": label}


# ------------------------------------------------------------------
# Analisi di una configurazione
# ------------------------------------------------------------------
def analyze(allSeries: list[dict], maxTime: int, delta: int = 100, ws=(1, 2, 5, 10, 20),
            nTaxi: int | None = None, idleTol: float = 0.01, **trendThresholds) -> dict:
    """Analisi completa. Restituisce:
        Y, ybar    : per metrica, matrice n x m e media verticale
        welch      : per metrica, {w: curva} per ogni w ammesso (w <= m/4)
        trend      : per metrica, blockCheck() sulla media verticale (solo per i grafici)
        unstableReplicas, pUnstable, label : test per replica (stabilityPerReplica; soglie relTol, absTol; più idle < idleTol * nTaxi)
        unstable   : True se almeno una replica è instabile (label != "stabile")
    """
    Y = buildMatrices(allSeries, maxTime, delta)
    m = Y[METRICS[0]].shape[1]
    ybar = {k: verticalMean(Y[k]) for k in METRICS}
    okWs = [w for w in ws if w <= m / 4]
    welch = {k: {w: welchMovingAverage(ybar[k], w) for w in okWs} for k in METRICS}
    trend = {k: blockCheck(Y[k], delta, maxTime, **trendThresholds) for k in METRICS}
    perRep = stabilityPerReplica(Y, delta, maxTime, nTaxi, idleTol, **trendThresholds)
    return {"delta": delta, "m": m, "ws": okWs, "Y": Y, "ybar": ybar,
            "welch": welch, "trend": trend, "unstable": perRep["pUnstable"] > 0,
            "pUnstable": perRep["pUnstable"], "label": perRep["label"],
            "unstableReplicas": perRep["unstableReplicas"]}
