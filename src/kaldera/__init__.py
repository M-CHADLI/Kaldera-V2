"""Kaldera — traitement des demandes de remboursement d'assurance par une équipe d'agents."""

from __future__ import annotations

from typing import Any

from . import metriques
from .bornes import bornes
from .superviseur import Superviseur

__all__ = ["bornes", "traiter_demande", "traiter_lot"]


def traiter_demande(
    demande: dict[str, Any], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite une demande et retourne sa fiche de décision."""
    return Superviseur(partenaire_url).traiter(demande)


def traiter_lot(
    demandes: list[dict[str, Any]], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite un lot de demandes ; retourne les fiches (dans l'ordre) et les métriques par agent."""
    fiches = [traiter_demande(d, partenaire_url=partenaire_url) for d in demandes]
    return {"fiches": fiches, "metriques": metriques.par_agent(fiches)}
