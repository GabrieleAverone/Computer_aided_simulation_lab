"""
Metodo di Welch (e MSER-5) per stimare la durata del warm-up.

Solo numpy: non dipende dalla simulazione. Gli input sono, per ogni replica, le
serie a tratti costanti registrate da Metrics.stateSeries():
    {"ends": [t1, t2, ...], "idleTaxi": [...], "queueInLoco": [...], "queueOnLine": [...]}
dove il valore k-esimo vale nell'intervallo [ends[k-1], ends[k]) (con ends[-1] = 0).

Passi:
  1. binStateSeries / buildMatrices : medie pesate nel tempo su intervalli di ampiezza delta
        Y[j, i] = (1/delta) * integrale di Q_j(t) su [(i-1)*delta, i*delta)
  2. verticalMean                   : Ybar[i] = media di Y[j, i] sulle repliche
  3. welchMovingAverage             : media mobile centrata con finestra 2w+1
  4. mser                           : stima automatica di l (MSER-5)
  5. trendCheck                     : la seconda metà della run ha ancora un trend crescente?
  6. deletionMeans                  : medie per replica dopo aver scartato i primi l passi
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
# 4. MSER-5
# ------------------------------------------------------------------
def mser(ybar: np.ndarray, delta: int, batch: int = 5, maxFraction: float = 0.5) -> dict:
    """MSER-5 sulla serie Ybar: raggruppa in batch da `batch` intervalli (media), poi sceglie
    il numero d di batch da scartare che minimizza
        sum_{j>d} (Z_j - Zbar_d)^2 / (k - d)^2
    con d <= maxFraction * k. Restituisce l in passi di simulazione (multiplo di batch*delta).
    `atLimit` = True se il minimo cade sul limite massimo: il warm-up non è ben determinato."""
    k = len(ybar) // batch
    if k < 4:
        raise ValueError(f"troppo pochi intervalli per MSER-{batch} (m={len(ybar)})")
    Z = ybar[:k * batch].reshape(k, batch).mean(axis=1)
    dMax = int(maxFraction * k)
    stats = []
    for d in range(dMax + 1):
        tail = Z[d:]
        stats.append(((tail - tail.mean()) ** 2).sum() / (k - d) ** 2)
    d = int(np.argmin(stats))                              # a parità: il d più piccolo
    return {"l": d * batch * delta, "d": d, "atLimit": d == dMax, "nBatches": k}


# ------------------------------------------------------------------
# 5. Controllo di stabilità
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


# ------------------------------------------------------------------
# Analisi di una configurazione
# ------------------------------------------------------------------
def analyze(allSeries: list[dict], maxTime: int, delta: int = 100, ws=(2, 5, 10, 20),
            trendW: int = 10, batch: int = 5) -> dict:
    """Analisi completa. Restituisce:
        Y, ybar    : per metrica, matrice n x m e media verticale
        welch      : per metrica, {w: curva} per ogni w ammesso (w <= m/4)
        mser       : per metrica, risultato di mser()
        trend      : per metrica, risultato di trendCheck()
        unstable   : True se almeno una metrica ha un trend crescente significativo
        warmup     : max delle l di MSER-5 tra le metriche (None se unstable)
    """
    Y = buildMatrices(allSeries, maxTime, delta)
    m = Y[METRICS[0]].shape[1]
    ybar = {k: verticalMean(Y[k]) for k in METRICS}
    okWs = [w for w in ws if w <= m / 4]
    welch = {k: {w: welchMovingAverage(ybar[k], w) for w in okWs} for k in METRICS}
    mserRes = {k: mser(ybar[k], delta, batch) for k in METRICS}
    wTrend = min(trendW, m // 4)
    trend = {k: trendCheck(Y[k], delta, wTrend, maxTime) for k in METRICS}
    unstable = any(t["unstable"] for t in trend.values())
    return {"delta": delta, "m": m, "ws": okWs, "trendW": wTrend, "Y": Y, "ybar": ybar,
            "welch": welch, "mser": mserRes, "trend": trend, "unstable": unstable,
            "warmup": None if unstable else max(r["l"] for r in mserRes.values())}


# ------------------------------------------------------------------
# 6. Stima con replication/deletion
# ------------------------------------------------------------------
def deletionMeans(allSeries: list[dict], l: float, maxTime: float) -> dict[str, list[float]]:
    """Per ogni replica e metrica: media pesata nel tempo su [l, maxTime]
    (i primi l passi sono scartati; l non deve essere multiplo di delta)."""
    out = {k: [] for k in METRICS}
    for s in allSeries:
        for k in METRICS:
            F = cumulativeIntegral(s, k, np.array([l, maxTime]))
            out[k].append(float(F[1] - F[0]) / (maxTime - l))
    return out


def cumulativeMeanFrom(series: dict, key: str, l: float, grid: np.ndarray) -> np.ndarray:
    """Media cumulativa da l a t per ogni t della griglia (t > l); NaN per t <= l."""
    F = cumulativeIntegral(series, key, np.concatenate(([l], grid)))
    out = np.full(len(grid), np.nan)
    ok = grid > l
    out[ok] = (F[1:][ok] - F[0]) / (grid[ok] - l)
    return out


def binEventMeans(times, values, maxTime: int, delta: int) -> np.ndarray:
    """Media dei valori (es. attese dei clienti) caduti in ciascun intervallo [(i-1)*delta, i*delta);
    NaN dove nell'intervallo non c'è nessun valore. Ogni valore è assegnato all'istante `times`."""
    m = maxTime // delta
    idx = (np.asarray(times, dtype=float) // delta).astype(int)
    ok = idx < m
    n = np.bincount(idx[ok], minlength=m)
    tot = np.bincount(idx[ok], weights=np.asarray(values, dtype=float)[ok], minlength=m)
    out = np.full(m, np.nan)
    out[n > 0] = tot[n > 0] / n[n > 0]
    return out
