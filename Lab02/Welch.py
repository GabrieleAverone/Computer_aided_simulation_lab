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
  4. trendCheck                     : la seconda metà della run ha ancora un trend crescente?
"""

import numpy as np

METRICS = ("idleTaxi", "queueInLoco", "queueOnLine")

# t di Student a una coda, 99% (df = 1..30; oltre: ~normale)
_T99_ONE_SIDED = [31.821, 6.965, 4.541, 3.747, 3.365, 3.143, 2.998, 2.896, 2.821, 2.764,
                  2.718, 2.681, 2.650, 2.624, 2.602, 2.583, 2.567, 2.552, 2.539, 2.528,
                  2.518, 2.508, 2.500, 2.492, 2.485, 2.479, 2.473, 2.467, 2.462, 2.457]


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
def _tCrit99(df: int) -> float:
    return _T99_ONE_SIDED[df - 1] if 1 <= df <= len(_T99_ONE_SIDED) else 2.326


def _slopes(X: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Pendenza OLS di ogni riga di X (n x p) rispetto a x (p)."""
    xc = x - x.mean()
    return (X - X.mean(axis=1, keepdims=True)) @ xc / (xc @ xc)


def trendCheck(Y: np.ndarray, delta: int, w: int, maxTime: int,
               relTol: float = 0.10, absTol: float = 0.10,
               strongRel: float = 0.40, strongAbs: float = 2.0) -> dict:
    """C'è ancora un trend crescente nella seconda metà della run?
    La pendenza è quella della regressione lineare sulla curva di Welch (finestra w), limitata ai
    punti con ascissa > maxTime/2; "aumento" = pendenza * maxTime/2. `unstable` se:
      (a) pendenza > 0 e aumento non trascurabile: > max(relTol * livello medio, absTol); e inoltre
      (b) il trend è "chiaro", in uno di due modi:
          - significativo: t-test a una coda (99%) sulle pendenze delle singole repliche (la curva
            di Welch è autocorrelata, le repliche no): funziona quando le repliche sono concordi;
          - netto: aumento >= strongRel * livello e >= strongAbs (in unità della metrica). Serve
            perché ogni replica ha stand in posizioni diverse: spesso solo alcune esplodono e le
            altre restano stazionarie, e il t sulla media (dominato da poche repliche) non le vede.
    Le soglie sono euristiche: vanno lette insieme al grafico di Welch."""
    n, m = Y.shape
    x = intervalCenters(m, delta)
    welch = welchMovingAverage(verticalMean(Y), w)
    xw = x[:len(welch)]
    sel = xw > maxTime / 2
    slopeWelch = float(_slopes(welch[sel][None, :], xw[sel])[0])
    level = float(np.mean(welch[sel]))
    rise = slopeWelch * maxTime / 2
    nonTrivial = bool(slopeWelch > 0 and rise > max(relTol * abs(level), absTol))

    xs = x > maxTime / 2
    perReplica = _slopes(Y[:, xs], x[xs])
    mean = float(perReplica.mean())
    if n >= 2:
        sd = float(perReplica.std(ddof=1))
        t = mean / (sd / np.sqrt(n)) if sd > 0 else (np.inf if mean > 0 else 0.0)
        significant = bool(t > _tCrit99(n - 1))
    else:                                                   # una sola replica: nessun test
        t, significant = float("nan"), mean > 0
    strong = bool(rise >= strongRel * abs(level) and rise >= strongAbs)

    return {"slope": slopeWelch, "rise": float(rise), "level": level, "t": float(t),
            "significant": significant, "strong": strong,
            "unstable": bool(nonTrivial and (significant or strong))}


def blockCheck(Y: np.ndarray, delta: int, maxTime: int, nBlocks: int = 4,
               relTol: float = 0.10, absTol: float = 0.10) -> dict:
    """Versione semplice di trendCheck: la media cresce blocco dopo blocco?
    Si prende la seconda metà della run (ascissa > maxTime/2), la si divide in nBlocks blocchi
    consecutivi e si calcola la media di Ybar (media sulle repliche) in ogni blocco.
    `unstable` se le medie dei blocchi crescono sempre (ogni blocco > il precedente) e l'aumento
    totale (ultimo - primo) supera max(relTol * livello medio, absTol)."""
    x = intervalCenters(Y.shape[1], delta)
    ybar = verticalMean(Y)[x > maxTime / 2]
    size = len(ybar) // nBlocks
    blocks = ybar[:size * nBlocks].reshape(nBlocks, size).mean(axis=1)
    level = float(blocks.mean())
    rise = float(blocks[-1] - blocks[0])
    increasing = bool(np.all(np.diff(blocks) > 0))
    return {"blocks": blocks, "level": level, "rise": rise, "increasing": increasing,
            "unstable": bool(increasing and rise > max(relTol * abs(level), absTol))}


# ------------------------------------------------------------------
# Analisi di una configurazione
# ------------------------------------------------------------------
def analyze(allSeries: list[dict], maxTime: int, delta: int = 100, ws=(1, 2, 5, 10, 20),
            trendW: int = 10, **trendThresholds) -> dict:
    """Analisi completa. Restituisce:
        Y, ybar    : per metrica, matrice n x m e media verticale
        welch      : per metrica, {w: curva} per ogni w ammesso (w <= m/4)
        trend      : per metrica, risultato di trendCheck() (trendThresholds = soglie: relTol, absTol, strongRel, strongAbs)
        unstable   : True se almeno una metrica ha un trend crescente significativo
    """
    Y = buildMatrices(allSeries, maxTime, delta)
    m = Y[METRICS[0]].shape[1]
    ybar = {k: verticalMean(Y[k]) for k in METRICS}
    okWs = [w for w in ws if w <= m / 4]
    welch = {k: {w: welchMovingAverage(ybar[k], w) for w in okWs} for k in METRICS}
    wTrend = min(trendW, m // 4)
    trend = {k: trendCheck(Y[k], delta, wTrend, maxTime, **trendThresholds) for k in METRICS}
    unstable = any(t["unstable"] for t in trend.values())
    return {"delta": delta, "m": m, "ws": okWs, "trendW": wTrend, "Y": Y, "ybar": ybar,
            "welch": welch, "trend": trend, "unstable": unstable}
