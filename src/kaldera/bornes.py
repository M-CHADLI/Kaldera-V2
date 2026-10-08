"""Bornes d'exécution provisoires (docs/conception/2-orchestration-memoire.md).

Fixées a priori ; toute modification est provoquée par un scénario d'épreuve et consignée
dans docs/journal-ajustements.md.
"""

from __future__ import annotations

from typing import Any

BORNES: dict[str, Any] = {
    # 9 étapes au pire (éligibilité, pièces, 2 × (complément + pièces), estimation,
    # anti-fraude, issue) + marge de 3.
    "etapes_max": 12,
    # Abandon de l'appel partenaire à 3 s + agents en millisecondes ; sous les 10 s du §12.
    "duree_max_s": 8.0,
    # NOM-07 a besoin d'un complément ; un second laisse une deuxième chance.
    "complements_max": 2,
    # Un dépôt identique à un dépôt précédent arrête la boucle (BCL-01).
    "depot_identique": True,
    "delai_partenaire_s": 3.0,
    "disjoncteur_echecs": 2,
}


def bornes() -> dict[str, Any]:
    """Bornes d'exécution en vigueur (docs/interface.md, « Bornes d'exécution »)."""
    return dict(BORNES)
