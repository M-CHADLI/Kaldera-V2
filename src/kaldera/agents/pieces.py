"""Pièces : les pièces exigées sont-elles présentes et lisibles ? (specs_metier.md, §5)

L'agent demande un complément ; c'est le superviseur qui l'exécute et qui borne la boucle.
"""

from __future__ import annotations

from typing import Any

from .. import regles
from .base import Resultat


class Pieces:
    nom = "pieces"
    section = "pieces"
    action = "verifier_pieces"

    def traiter(self, vue: dict[str, Any]) -> Resultat:
        recues = vue["pieces"]
        a_redemander = []
        for type_piece in regles.PIECES_EXIGEES[vue["type_sinistre"]]:
            du_type = [p for p in recues if p.get("type") == type_piece]
            if not du_type or not du_type[-1].get("lisible", False):
                a_redemander.append(type_piece)
        factures = [
            float(p["montant"])
            for p in recues
            if p.get("type") == "facture" and p.get("lisible") and _est_montant(p.get("montant"))
        ]
        valeur = {
            "conformes": not a_redemander,
            "a_redemander": a_redemander,
            "sans_depot": list(vue["sans_depot"]),
            "factures": factures,
        }
        if not a_redemander:
            return Resultat("conclu", valeur)
        if vue["sans_depot"]:
            # L'assuré n'a rien déposé du type demandé : plus rien à attendre (§5).
            return Resultat("conclu", valeur, motif="aucun dépôt de l'assuré")
        return Resultat("complement_requis", valeur)


def _est_montant(valeur: Any) -> bool:
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
