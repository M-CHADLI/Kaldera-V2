"""Anti-fraude : faut-il consulter le partenaire, et que dit-il ? (specs_metier.md, §7)

Calcule les indicateurs F1 à F4 (un déclencheur, pas un jugement) et transmet l'avis validé
du partenaire. N'émet jamais d'avis lui-même et ne recopie jamais une réponse rejetée.
"""

from __future__ import annotations

from typing import Any, Callable

from .. import regles
from ..partenaire import Consultation
from .base import Resultat

Consulter = Callable[[dict[str, Any]], Consultation]


class AntiFraude:
    nom = "antifraude"
    section = "avis_fraude"
    action = "evaluer_risque"

    def __init__(self, consulter: Consulter) -> None:
        self._consulter = consulter

    def traiter(self, vue: dict[str, Any]) -> Resultat:
        donnees = vue["donnees_contrat"]
        indicateurs = indicateurs_risque(donnees, vue["montant_justifie"])
        if not indicateurs:
            return Resultat("conclu", {"statut": "non_requis", "indicateurs": []})
        consultation = self._consulter(donnees)
        appels = int(consultation.appel_effectue)
        if consultation.avis is None:
            return Resultat(
                "conclu",
                {
                    "statut": "indisponible",
                    "indicateurs": indicateurs,
                    "rejet": {"couche": consultation.couche, "raison": consultation.raison},
                },
                appels_externes=appels,
                echec=True,
            )
        avis = consultation.avis
        return Resultat(
            "conclu",
            {
                "statut": "obtenu",
                "indicateurs": indicateurs,
                "niveau": avis["niveau"],
                "score": avis["score"],
                "evaluation_id": avis["evaluation_id"],
            },
            appels_externes=appels,
        )


def indicateurs_risque(donnees: dict[str, Any], montant_justifie: float) -> list[str]:
    """Indicateurs F1 à F4 présents dans la demande (§7)."""
    montant = donnees["montant_declare"]
    indicateurs = []
    if montant >= regles.SEUIL_MONTANT_FRAUDE:
        indicateurs.append("F1")
    if donnees["anciennete_contrat_jours"] < regles.ANCIENNETE_SENSIBLE_JOURS:
        indicateurs.append("F2")
    if donnees["sinistres_12_mois"] >= regles.FREQUENCE_SENSIBLE:
        indicateurs.append("F3")
    if montant > montant_justifie * (1 + regles.ECART_DECLARATION_MAX):
        indicateurs.append("F4")
    return indicateurs
