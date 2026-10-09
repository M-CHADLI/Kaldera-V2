"""Kaldera — traitement des demandes de remboursement d'assurance par une équipe d'agents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import historique, metriques
from .bornes import BORNES, bornes
from .partenaire import ClientPartenaire
from .superviseur import Superviseur

__all__ = ["bornes", "traiter_demande", "traiter_lot"]

MAX_DEMANDES_EN_PARALLELE = 8


def traiter_demande(
    demande: dict[str, Any], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite une demande et retourne sa fiche de décision, versée à l'historique."""
    fiche = Superviseur(partenaire_url).traiter(demande)
    historique.enregistrer(demande, fiche)
    return fiche


def traiter_lot(
    demandes: list[dict[str, Any]], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite un lot de demandes en parallèle : aucune n'attend les autres (§12).

    Retourne les fiches, dans l'ordre des demandes, et les métriques par agent.
    """
    client = ClientPartenaire(
        partenaire_url,
        delai_s=BORNES["delai_partenaire_s"],
        seuil_pannes=BORNES["disjoncteur_echecs"],
    )

    def traiter(demande: dict[str, Any]) -> dict[str, Any]:
        fiche = Superviseur(partenaire_url, client=client).traiter(demande)
        historique.enregistrer(demande, fiche)
        return fiche

    if not demandes:
        return {"fiches": [], "metriques": {}}
    with ThreadPoolExecutor(max_workers=min(MAX_DEMANDES_EN_PARALLELE, len(demandes))) as pool:
        fiches = list(pool.map(traiter, demandes))
    return {"fiches": fiches, "metriques": metriques.par_agent(fiches)}
