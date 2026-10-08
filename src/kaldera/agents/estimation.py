"""Estimation : combien l'assureur rembourse-t-il ? (specs_metier.md, §6, et plafond du §4)

Point de frontière tranché : le plafond de garantie, rangé au §4 avec l'éligibilité, porte
sur un montant. C'est donc l'Estimation qui l'applique et le signale (NOM-05).
Ne juge jamais la fraude.
"""

from __future__ import annotations

from typing import Any

from .base import Resultat


class Estimation:
    nom = "estimation"
    section = "estimation"
    action = "estimer"

    def traiter(self, vue: dict[str, Any]) -> Resultat:
        montants = calculer_montant(
            vue["montant_declare"], vue["factures"], vue["franchise"], vue["plafond"]
        )
        return Resultat("conclu", {"formule": vue["formule"], **montants})


def calculer_montant(
    montant_declare: float, factures: list[float], franchise: float, plafond: float
) -> dict[str, Any]:
    """Calcule le montant estimé d'une demande (§6), plafond du §4 compris.

    Retourne un dictionnaire avec ces clés, montants arrondis au centime :
    - ``montant_justifie`` : somme des factures lisibles ;
    - ``montant_retenu`` : le plus petit du montant déclaré et du montant justifié ;
    - ``montant_estime`` : ce que l'assureur rembourse, jamais négatif ;
    - ``plafond`` : le plafond de la formule ;
    - ``plafond_applique`` : True si le plafond a réduit le montant estimé.

    Exemple NOM-05 (formule essentiel) : déclaré 4 200, factures [4 200], franchise 300,
    plafond 3 000 → montant estimé 3 000, plafond appliqué.
    """
    justifie = round(sum(factures), 2)
    retenu = min(montant_declare, justifie)
    # La franchise d'abord, le plafond ensuite : NOM-05 attend 4 200 − 300 = 3 900 → 3 000.
    avant_plafond = round(max(0.0, retenu - franchise), 2)
    estime = min(avant_plafond, plafond)
    return {
        "montant_justifie": justifie,
        "montant_retenu": round(retenu, 2),
        "montant_estime": estime,
        "plafond": plafond,
        "plafond_applique": estime < avant_plafond,
    }
