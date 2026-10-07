"""Kaldera — traitement des demandes de remboursement d'assurance."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from .orchestrateur import Orchestrateur

__all__ = ["traiter_demande", "traiter_lot"]


def traiter_demande(
    demande: dict[str, Any], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite une demande et retourne sa fiche de décision."""
    return Orchestrateur(partenaire_url).traiter(demande)


def traiter_lot(
    demandes: list[dict[str, Any]], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite un lot de demandes ; retourne les fiches (dans l'ordre) et les métriques."""
    debut = perf_counter()
    fiches = [traiter_demande(d, partenaire_url=partenaire_url) for d in demandes]
    return {
        "fiches": fiches,
        "metriques": {
            "demandes": len(fiches),
            "duree_totale_ms": round((perf_counter() - debut) * 1000, 2),
        },
    }
