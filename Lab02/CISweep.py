"""Intervalli di confidenza al variare dei parametri, a partire da results.csv (una riga per replica).
Funzioni pure su DataFrame: niente simulazione; matplotlib viene importato solo da plotSweep."""

import numpy as np
import pandas as pd
from scipy import stats

# colonne di results.csv che sono parametri del modello
PARAM_COLS = ["nStand", "nTaxi", "capacity", "capacitySlack", "policy", "redistribution", "rebalance",
              "rebalanceReserve", "reachProb", "arrivalRate", "minTripDistance", "minStandDistance",
              "maxTime", "warmupTime"]


def varyingParams(df: pd.DataFrame) -> list[str]:
    """Parametri che assumono più di un valore nel DataFrame."""
    return [c for c in PARAM_COLS if c in df.columns and df[c].nunique() > 1]


def summarize(df: pd.DataFrame, metrics: list[str], confidence: float = 0.95,
              groupBy: list[str] | None = None) -> pd.DataFrame:
    """Una riga per (runId + parametri variabili): per ogni metrica mean, ci (semi-ampiezza),
    rel (ci/|mean|), più n (repliche) e, se presente nel CSV, `stable`. Con n < 2 ci e rel sono NaN."""
    keys = ["runId"] + (varyingParams(df) if groupBy is None else groupBy)
    g = df.groupby(keys, dropna=False)
    out = pd.DataFrame({"n": g[metrics[0]].count()})
    t = stats.t.ppf(1 - (1 - confidence) / 2, (out["n"] - 1).clip(lower=1))
    for m in metrics:
        out[f"{m}_mean"] = g[m].mean()
        out[f"{m}_ci"] = (t * g[m].std() / np.sqrt(out["n"])).where(out["n"] >= 2)    # std: ddof=1
        out[f"{m}_rel"] = out[f"{m}_ci"] / out[f"{m}_mean"].abs()
    if "stable" in df.columns:
        out["stable"] = g["stable"].first()
    return out.reset_index()


def sweep(df: pd.DataFrame, param: str, metric: str, confidence: float = 0.95,
          onlyStable: bool = False) -> pd.DataFrame:
    """Tabella per il grafico metrica-contro-`param`: una riga per (valore di `param`, combinazione degli altri
    parametri variabili), con mean, ci, rel, n, stable e `series` (etichetta degli altri parametri, "" se nessuno).
    `onlyStable` scarta le run non stabili."""
    if param not in df.columns:
        raise ValueError(f"parametro sconosciuto: {param}")
    others = [c for c in varyingParams(df) if c != param]
    s = summarize(df, [metric], confidence, groupBy=[param] + others)
    s = s.rename(columns={f"{metric}_{k}": k for k in ("mean", "ci", "rel")})
    if onlyStable and "stable" in s:
        s = s[s["stable"].astype(str) == "True"]
    s["series"] = [", ".join(f"{c}={v}" for c, v in zip(others, vals)) for vals in s[others].itertuples(index=False)]
    return s.sort_values(["series", param]).reset_index(drop=True)


def plotSweep(table: pd.DataFrame, param: str, metric: str, confidence: float = 0.95, ax=None):
    """Media ± IC contro `param`, una linea per serie. Le run instabili sono cerchi vuoti (IC non affidabile)."""
    import matplotlib.pyplot as plt
    ax = ax or plt.subplots(figsize=(8, 4.5))[1]
    for k, (name, part) in enumerate(table.groupby("series")):
        ax.errorbar(part[param], part["mean"], yerr=part["ci"], color=f"C{k}", capsize=3, lw=1,
                    label=name or "tutte le run")
        if "stable" in part:
            bad = part[part["stable"].astype(str) == "False"]
            ax.plot(bad[param], bad["mean"], "o", mfc="white", mec=f"C{k}", ms=9)
    ax.set(xlabel=param, ylabel=f"{metric} (media ± IC {confidence:.0%})")
    ax.grid(True, alpha=0.3)
    if table["series"].any():
        ax.legend(fontsize=8)
    ax.figure.tight_layout()
    return ax
