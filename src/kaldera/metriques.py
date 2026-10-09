"""Métriques par agent, calculées à partir des traces (docs/interface.md, « Métriques »).

``anomalies`` compte les signaux ``anomalie`` de la revue de fond du superviseur (``revue.py``) :
un simple signal, qui n'a changé aucune valeur ni aucune issue.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def par_agent(fiches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "appels": 0,
            "echecs": 0,
            "latence_ms": 0.0,
            "appels_externes": 0,
            "anomalies": 0,
        }
    )
    durees: dict[str, list[float]] = defaultdict(list)
    for fiche in fiches:
        for etape in fiche.get("trace", []):
            agent = etape["agent"]
            stats[agent]["appels"] += 1
            stats[agent]["echecs"] += int(bool(etape.get("echec")))
            stats[agent]["appels_externes"] += int(etape.get("appels_externes", 0))
            stats[agent]["anomalies"] += int(_anomalie(etape))
            durees[agent].append(float(etape.get("duree_ms", 0.0)))
    for agent, valeurs in durees.items():
        stats[agent]["latence_ms"] = round(sum(valeurs) / len(valeurs), 2)
    return dict(stats)


def _anomalie(etape: dict[str, Any]) -> bool:
    revue = etape.get("revue")
    return isinstance(revue, dict) and revue.get("statut") == "anomalie"
