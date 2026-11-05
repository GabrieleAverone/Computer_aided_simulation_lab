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
                     nTaxi: int | None = None, idleTol: float = 0.01, **trendThresholds: float) -> dict:
    """Curve di Welch + controllo a blocchi nella seconda metà della run.
    Il test è per replica: status = "stable" / "metastable" / "unstable" (label stabile/metastabile/instabile),
    pUnstable = frazione di repliche con una coda che cresce o con taxi liberi < idleTol * nTaxi."""
    a = Welch.analyze(stateSeries, maxTime, delta, ws, nTaxi, idleTol, **trendThresholds)
    status = {"stabile": "stable", "metastabile": "metastable", "instabile": "unstable"}[a["label"]]
    return {"status": status, "unstable": a["unstable"], "pUnstable": a["pUnstable"], "label": a["label"],
            "unstableReplicas": a["unstableReplicas"],
            "delta": delta, "ws": a["ws"], "trend": a["trend"], "analysis": a}


def printWelch(r: dict) -> None:
    print(f"    --- stabilità (Welch, delta={r['delta']}) ---")
    for k in Welch.METRICS:
        t = r["trend"][k]
        flag = "  <-- trend crescente (media)" if t["unstable"] and k in Welch.QUEUE_METRICS else ""
        blocks = " -> ".join(f"{b:.3f}" for b in t["blocks"])
        print(f"    {k}: 2a metà a blocchi (media repliche): {blocks} (aumento {t['rise']:+.3f}){flag}")
    n = len(r["unstableReplicas"])
    print(f"    repliche instabili: {int(r['unstableReplicas'].sum())}/{n} (pUnstable = {r['pUnstable']:.2f})")
    print("    ESITO: " + {"stable": "STABILE (nessuna replica con coda crescente o taxi saturi nella 2a metà)",
                           "metastable": "METASTABILE (alcune repliche con coda crescente o taxi sempre occupati)",
                           "unstable": "INSTABILE (tutte le repliche con coda crescente)"}[r["status"]])
