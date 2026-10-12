"""Pièces : les pièces exigées sont-elles présentes, lisibles et cohérentes avec la déclaration ?
(specs_metier.md, §5)

L'agent demande un complément ; c'est le superviseur qui l'exécute et qui borne la boucle.
Une incohérence ne se corrige pas par un nouveau dépôt : elle est signalée, et la décision
l'escalade vers un gestionnaire.
"""

from __future__ import annotations

from typing import Any

from .. import regles
from .base import Resultat


NON_ANALYSEES = ("photo",)


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
            # Pièces reçues dont le contenu n'est pas jugé par le système : un humain les examine.
            "non_analysees": sorted({p["type"] for p in recues if p.get("type") in NON_ANALYSEES}),
            "incoherences": incoherences(vue.get("date_survenance"), recues),
        }
        if not a_redemander:
            return Resultat("conclu", valeur)
        if vue["sans_depot"]:
            # L'assuré n'a rien déposé du type demandé : plus rien à attendre (§5).
            return Resultat("conclu", valeur, motif="aucun dépôt de l'assuré")
        return Resultat("complement_requis", valeur)


def incoherences(survenance: str | None, pieces: list[dict[str, Any]]) -> list[str]:
    """Écarts entre les dates portées par les pièces et la survenance déclarée (§5).

    Seules des dates qui désignent le sinistre lui-même sont comparées : les faits d'une plainte
    et le sinistre cité par une facture. La date d'émission d'une facture n'est jamais un
    critère : une facture d'achat antérieure (valeur d'un bien détruit ou volé) est légitime,
    comme une facture de serrurier postérieure à un vol. Une date absente n'est pas comparée.
    """
    if not survenance:
        return []
    tolerance = regles.TOLERANCE_DATES_PIECES_JOURS
    motifs: list[str] = []
    for p in pieces:
        if not p.get("lisible"):
            continue
        cite = p.get("date_sinistre") if p.get("type") == "facture" else None
        if _ecart(survenance, cite) > tolerance:
            motifs.append(f"facture visant un sinistre du {cite}, déclaré survenu le {survenance}")
        if p.get("type") != "depot_plainte":
            continue
        faits, depot = p.get("date_faits"), p.get("date_depot")
        if _ecart(survenance, faits) > tolerance:
            motifs.append(f"plainte pour des faits du {faits}, sinistre déclaré le {survenance}")
        if _ecart(faits, depot, signe=True) < 0:
            motifs.append(f"plainte déposée le {depot}, avant les faits du {faits}")
    return motifs


def _ecart(debut: Any, fin: Any, signe: bool = False) -> int:
    """Jours de ``debut`` à ``fin`` (en valeur absolue sauf ``signe``) ; 0 si une date manque
    ou est mal formée : on ne conclut jamais à une incohérence sur une date qu'on ne sait pas lire."""
    try:
        jours = regles.jours_entre(str(debut), str(fin)) if debut and fin else 0
    except ValueError:
        return 0
    return jours if signe else abs(jours)


def _est_montant(valeur: Any) -> bool:
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
