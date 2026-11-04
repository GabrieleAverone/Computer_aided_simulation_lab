
import numpy as np
 
# =====================================================================
# UNITÀ DI MISURA (valgono per tutto il simulatore)
#   - spazio: 1 cella = CELL_SIZE_KM km  -> mappa 100x100 = 10 km x 10 km
#   - tempo:  interi, 1 passo = TIME_STEP_MIN minuti (tempo discreto)
# I parametri sono in unità "fisiche" (km/h, clienti/minuto) e vengono
# convertiti in passi qui sotto, così non ci sono numeri magici.
# =====================================================================
 
# --- mappa ---
MAP_WIDTH = 100               # x in [0, MAP_WIDTH - 1]
MAP_HEIGHT = 100              # y in [0, MAP_HEIGHT - 1]
CELL_SIZE_KM = 0.1            # 100 m per cella
 
# --- tempo discreto ---
TIME_STEP_MIN = 0.25          # durata di un passo in minuti (es. 0.25 = 15 s)
 
# --- arrivi ---
ARRIVAL_RATE = 2 / 5         # λ [clienti/minuto]: in media 1 cliente ogni 5 min
# probabilità che in un passo arrivi un cliente (deve essere <= 1)
ARRIVAL_PROB_PER_STEP = ARRIVAL_RATE * TIME_STEP_MIN
assert 0 < ARRIVAL_PROB_PER_STEP <= 1, "riduci TIME_STEP_MIN o ARRIVAL_RATE"
 
# --- velocità medie (km/h) e variabilità relativa (±) ---
FOOT_SPEED_KMH = 5.0
FOOT_SPEED_VARIATION = 0.15   # ±15%: chi cammina varia poco
TAXI_SPEED_KMH = 30.0
TAXI_SPEED_VARIATION = 0.30   # ±30%: traffico
 
# --- modalità test ---
# Moltiplica tutte le velocità: con 1 i tempi sono "realistici", con valori
# più alti i viaggi si accorciano e si vedono più eventi in meno passi.
# Il rapporto taxi/piedi resta invariato. Rimetti 1 per le simulazioni vere.
SPEEDUP = 1
 
# conversione: passi necessari per attraversare una cella a velocità media
FOOT_STEPS_PER_CELL = CELL_SIZE_KM / (FOOT_SPEED_KMH * SPEEDUP) * 60 / TIME_STEP_MIN
TAXI_STEPS_PER_CELL = CELL_SIZE_KM / (TAXI_SPEED_KMH * SPEEDUP) * 60 / TIME_STEP_MIN
 
# --- generatore casuale unico ---
# Un solo generatore per tutta la simulazione: per fare repliche
# indipendenti chiama setSeed() con un seed diverso prima di ogni run.
rng = np.random.default_rng(42)
 
 
def setSeed(seed) -> None:
    # seed: un intero o un np.random.SeedSequence
    global rng
    rng = np.random.default_rng(seed)
 
 
def manhattanDistance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
 
 
def getNewSpawnTime(arrivalProb: float = ARRIVAL_PROB_PER_STEP) -> int:
    """Interarrivo fino al prossimo cliente, in passi: Geometrica(p) su {1, 2, ...}.
    È l'equivalente a tempo discreto dell'esponenziale (senza memoria),
    con media esatta 1/p = 1/(λ·passo). Restituisce un intervallo: il
    chiamante fa now + valore."""
    return int(rng.geometric(arrivalProb))
 
 
def getNewLocation() -> tuple[int, int]:
    """Cella uniforme sulla mappa."""
    return (int(rng.integers(0, MAP_WIDTH)), int(rng.integers(0, MAP_HEIGHT)))
 
 
def _travelTime(startCoord, endCoord, stepsPerCell: float, variation: float) -> int:
    """Tempo di viaggio in passi = distanza x passi per cella, arrotondato.
    La velocità del singolo viaggio è uniforme in [v(1-δ), v(1+δ)].
    Un viaggio con distanza > 0 dura almeno 1 passo; distanza 0 dura 0."""
    dist = manhattanDistance(startCoord, endCoord)
    if dist == 0:
        return 0
    speedFactor = rng.uniform(1 - variation, 1 + variation)
    return max(1, round(dist * stepsPerCell / speedFactor))
 
 
def getTimeByFoot(startCoord: tuple[int, int], endCoord: tuple[int, int]) -> int:
    return _travelTime(startCoord, endCoord, FOOT_STEPS_PER_CELL, FOOT_SPEED_VARIATION)
 
 
def getTimeByTaxi(startCoord: tuple[int, int], endCoord: tuple[int, int]) -> int:
    return _travelTime(startCoord, endCoord, TAXI_STEPS_PER_CELL, TAXI_SPEED_VARIATION)
 
 
def coinToss(p: float) -> bool:
    if not 0 <= p <= 1:
        raise ValueError(f"p deve essere tra 0 e 1, ricevuto {p}")
    return bool(rng.random() < p)
