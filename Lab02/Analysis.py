"""Analisi statistica dei risultati: medie e intervalli di confidenza, warm-up (Welch + MSER-5),
controllo di stabilità. Non dipende da matplotlib né dalla simulazione: lavora su serie e report."""

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



def analyzeWarmup(stateSeries: list[dict], maxTime: int, delta: int, ws: tuple[int, ...],
                  manualWarmup: int | None, stabilityOnly: bool = False) -> dict:
    """Welch + MSER-5 + controllo di stabilità + stima finale (replication/deletion).
    status: "ok" (l stimato), "unstable" (nessun warm-up restituito), "manual" (l passato a mano)."""
    a = Welch.analyze(stateSeries, maxTime, delta, ws)
    if stabilityOnly:
        # solo stabilità: curve di Welch e controllo di trend; niente MSER-5, warm-up l e stima finale.
        # status: "stable" (nessun trend crescente nella 2a metà) oppure "unstable"
        return {"warmup": None, "status": "unstable" if a["unstable"] else "stable", "unstable": a["unstable"],
                "delta": delta, "ws": a["ws"], "mser": None, "mserAtLimit": [],
                "trend": a["trend"], "estimate": None, "analysis": a}
    if manualWarmup is not None:
        l, status = manualWarmup, "manual"
    elif a["unstable"]:
        l, status = None, "unstable"
    else:
        l, status = a["warmup"], "ok"

    estimate = None
    if l is not None:
        if not 0 <= l < maxTime:
            raise ValueError("warmup deve essere in [0, maxTime)")
        means = Welch.deletionMeans(stateSeries, l, maxTime)
        estimate = {key: dict(zip(("mean", "ci"), meanAndCI(vals))) for key, vals in means.items()}

    return {"warmup": l, "status": status, "unstable": a["unstable"], "delta": delta, "ws": a["ws"],
            "mser": {k: r["l"] for k, r in a["mser"].items()},
            "mserAtLimit": [k for k, r in a["mser"].items() if r["atLimit"]],
            "trend": a["trend"], "estimate": estimate, "analysis": a}



def printWelch(r: dict) -> None:
    if r["mser"] is None:                                   # modalità stabilityOnly
        print(f"    --- stabilità (Welch, delta={r['delta']}) ---")
        for k in Welch.METRICS:
            t = r["trend"][k]
            flag = "  <-- trend crescente" if t["unstable"] else ""
            print(f"    {k}: 2a metà: livello {t['level']:.3f}, aumento {t['rise']:+.3f} "
                  f"(pendenza {t['slope']:.2e}/passo, t={t['t']:.2f}){flag}")
        print("    ESITO: " + ("INSTABILE (trend crescente: nessuno stato stazionario)" if r["unstable"]
                              else "STABILE (nessun trend crescente nella 2a metà)"))
        return
    print(f"    --- warm-up (Welch, delta={r['delta']}, MSER-5) ---")
    for k in Welch.METRICS:
        t = r["trend"][k]
        flag = "  <-- trend crescente" if t["unstable"] else ""
        print(f"    {k}: MSER-5 l={r['mser'][k]}, 2a metà: livello {t['level']:.3f}, "
              f"aumento {t['rise']:+.3f} (pendenza {t['slope']:.2e}/passo, t={t['t']:.2f}){flag}")
    if r["mserAtLimit"]:
        print(f"    attenzione: MSER-5 sul limite massimo per {r['mserAtLimit']} (warm-up non ben determinato)")
    if r["status"] == "unstable":
        print("    ESITO: probabilmente instabile / nessuno stato stazionario -> nessun warm-up restituito")
        return
    origin = "manuale" if r["status"] == "manual" else "max tra le metriche"
    print(f"    ESITO: warm-up l = {r['warmup']} passi ({origin})"
          + ("  [ATTENZIONE: la configurazione sembra instabile]" if r["unstable"] else ""))
    print("    stima replication/deletion (media ± IC95%, dati dopo l):")
    for k, e in r["estimate"].items():
        print(f"      {k}: {e['mean']:.4f} ± {e['ci']:.4f}")
