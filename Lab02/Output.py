"""Salvataggio dei risultati: results.csv.
Funzioni senza stato: ricevono cartelle e parametri della run come argomenti."""

import csv
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:               # solo per le annotazioni (evita l'import circolare con Simulation)
    from Simulation import Parameters


def saveResults(outDir: Path, p: "Parameters", runId: str, seed: int, globalReports: list[dict],
                warmupEnd: list[int] | None = None) -> None:
    """Aggiunge a results.csv una riga per replica (un solo file per tutte le run).
    `warmupEnd`: tempo di simulazione in cui finisce il warm-up (inizio della finestra di misura) per replica."""
    params = asdict(p)
    params["capacity"] = "-".join(str(c) for c in p.capacityList())
    columns = ["runId", "replica", "seed"] + list(params) + list(globalReports[0]) + ["warmupEnd"]

    path = outDir / "results.csv"
    if path.exists() and path.stat().st_size > 0:
        with open(path, newline="") as f:
            oldColumns = next(csv.reader(f))
        if oldColumns != columns:
            # file vecchio: si completa solo se mancano parametri nuovi (valore di default) o `warmupEnd` (vuoto)
            defaults = {k: str(v) for k, v in asdict(type(p)()).items()}
            missing = [c for c in columns if c not in oldColumns]
            if [c for c in oldColumns if c not in columns] or any(c not in defaults and c != "warmupEnd" for c in missing):
                raise ValueError(f"{path} ha colonne diverse da quelle attuali: "
                                 "cambia outDir o rinomina il vecchio file")
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for row in rows:
                    writer.writerow({**{c: defaults.get(c, "") for c in missing}, **row})
    else:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(columns)

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        for i, g in enumerate(globalReports):
            writer.writerow({"runId": runId, "replica": i, "seed": seed, **params, **g,
                             "warmupEnd": "" if warmupEnd is None else warmupEnd[i]})
