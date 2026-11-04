"""Analisi statistica dei risultati: medie e intervalli di confidenza, metodo di Welch e controllo di stabilità. Non dipende da matplotlib né dalla simulazione: lavora su serie e report."""

import Welch


# t di Student, 95% bilaterale, per df = 1..30 (oltre: ~normale)
_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def meanAndCI(values: list[float]) -> tuple[float, float]:
    """Media e semi-ampiezza dell'intervallo di confidenza al 95%."""
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, float("nan")
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    t = _T95[n - 2] if n - 1 <= len(_T95) else 1.96
    return mean, t * (var / n) ** 0.5



def analyzeStability(stateSeries: list[dict], maxTime: int, delta: int, ws: tuple[int, ...],
                     **trendThresholds: float) -> dict:
    """Curve di Welch + controllo di trend nella seconda metà della run.
    status: "stable" (nessun trend crescente) oppure "unstable"."""
    a = Welch.analyze(stateSeries, maxTime, delta, ws, **trendThresholds)
    return {"status": "unstable" if a["unstable"] else "stable", "unstable": a["unstable"],
            "delta": delta, "ws": a["ws"], "trend": a["trend"], "analysis": a}


def printWelch(r: dict) -> None:
    print(f"    --- stabilità (Welch, delta={r['delta']}) ---")
    for k in Welch.METRICS:
        t = r["trend"][k]
        flag = "  <-- trend crescente" if t["unstable"] else ""
        print(f"    {k}: 2a metà: livello {t['level']:.3f}, aumento {t['rise']:+.3f} "
              f"(pendenza {t['slope']:.2e}/passo, t={t['t']:.2f}){flag}")
    print("    ESITO: " + ("INSTABILE (trend crescente: nessuno stato stazionario)" if r["unstable"]
                          else "STABILE (nessun trend crescente nella 2a metà)"))
