"""Éligibilité : le contrat couvre-t-il ce sinistre ? (specs_metier.md, §4)

Ne chiffre jamais la demande : le plafond de garantie est appliqué par l'Estimation.
"""

from __future__ import annotations

from typing import Any

from .. import regles
from .base import Resultat


class Eligibilite:
    nom = "eligibilite"
    section = "eligibilite"
    action = "verifier_eligibilite"

    def traiter(self, vue: dict[str, Any]) -> Resultat:
        formule = regles.FORMULES[vue["formule"]]
        motifs = []
        if vue["statut_contrat"] != "actif":
            motifs.append("contrat non actif")
        if not vue["cotisations_a_jour"]:
            motifs.append("cotisations impayées")
        anciennete = regles.jours_entre(vue["date_souscription"], vue["date_survenance"])
        if anciennete < regles.CARENCE_JOURS:
            motifs.append(f"sinistre survenu pendant la carence ({anciennete} jours sur 30)")
        delai = regles.jours_entre(vue["date_survenance"], vue["date_declaration"])
        delai_max = (
            regles.DELAI_DECLARATION_VOL_JOURS
            if vue["type_sinistre"] == "vol"
            else regles.DELAI_DECLARATION_JOURS
        )
        if delai > delai_max:
            motifs.append(f"déclaration hors délai ({delai} jours pour {delai_max} autorisés)")
        if vue["type_sinistre"] not in formule["garanties"]:
            motifs.append(f"sinistre non couvert par la formule {vue['formule']}")
        return Resultat("conclu", {"eligible": not motifs, "motifs": motifs})
