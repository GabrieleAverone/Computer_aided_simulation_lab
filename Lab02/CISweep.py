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
    rel (ci/|mean|), più n (repliche) e, se presente nel CSV, `stable`.
    Con n < 2 repliche ci e rel sono NaN."""
    keys = ["runId"] + (varyingParams(df) if groupBy is None else groupBy)
    g = df.groupby(keys, dropna=False)
    n = g[metrics[0]].count()
    out = pd.DataFrame({"n": n})
    for m in metrics:
        mean, std = g[m].mean(), g[m].std(ddof=1)
        t = pd.Series(stats.t.ppf(1 - (1 - confidence) / 2, (n - 1).clip(lower=1)), index=n.index)
        ci = (t * std / np.sqrt(n)).where(n >= 2)
        out[f"{m}_mean"], out[f"{m}_ci"] = mean, ci
        out[f"{m}_rel"] = (ci / mean.abs()).where(mean != 0)
    if "stable" in df.columns:
        out["stable"] = g["stable"].first()
    return out.reset_index()


def sweep(df: pd.DataFrame, param: str, metric: str, confidence: float = 0.95,
          onlyStable: bool = False) -> pd.DataFrame:
    """Tabella per un grafico metrica-contro-parametro: una riga per (valore di `param`, combinazione
    degli altri parametri variabili), con colonne mean, ci, rel, n, stable e `series` (etichetta
    degli altri parametri, "" se non ce ne sono). `onlyStable` scarta le run non stabili."""
    if param not in df.columns:
        raise ValueError(f"parametro sconosciuto: {param}")
    others = [c for c in varyingParams(df) if c != param]
    s = summarize(df, [metric], confidence, groupBy=[param] + others)
    s = s.rename(columns={f"{metric}_mean": "mean", f"{metric}_ci": "ci", f"{metric}_rel": "rel"})
    if onlyStable and "stable" in s.columns:
        s = s[s["stable"].astype(str) == "True"]
    s["series"] = s[others].apply(lambda r: ", ".join(f"{c}={v}" for c, v in r.items()), axis=1) if others else ""
    return s.sort_values(["series", param]).reset_index(drop=True)


def plotSweep(table: pd.DataFrame, param: str, metric: str, confidence: float = 0.95, ax=None):
    """Media ± IC contro `param`, una linea per serie. Le run instabili sono punti vuoti (IC non affidabile)."""
    import matplotlib.pyplot as plt
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4.5))
    for k, (name, part) in enumerate(table.groupby("series")):
        color = f"C{k}"
        ax.errorbar(part[param].astype(float) if pd.api.types.is_numeric_dtype(part[param]) else range(len(part)),
                    part["mean"], yerr=part["ci"], color=color, capsize=3, lw=1, label=name or "tutte le run")
        if "stable" in part.columns:
            bad = part["stable"].astype(str) == "False"
            if bad.any() and pd.api.types.is_numeric_dtype(part[param]):
                ax.plot(part.loc[bad, param], part.loc[bad, "mean"], "o", mfc="white", mec=color, ms=9)
    ax.set_xlabel(param)
    ax.set_ylabel(f"{metric} (media ± IC {confidence:.0%})")
    ax.grid(True, alpha=0.3)
    if table["series"].astype(bool).any():
        ax.legend(fontsize=8)
    ax.figure.tight_layout()
    return ax
