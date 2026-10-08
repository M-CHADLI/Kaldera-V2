"""Règles de décision (specs_metier.md, §10), mode dégradé (§9) compris.

Code déterministe appelé par le superviseur comme un outil : les montants et les files ne
dépendent d'aucun modèle de langage.
"""

from __future__ import annotations

from typing import Any

from . import regles


def decider(
    eligibilite: dict[str, Any],
    pieces: dict[str, Any] | None,
    estimation: dict[str, Any] | None,
    avis: dict[str, Any] | None,
) -> dict[str, Any]:
    """Applique les règles du §10 dans l'ordre ; la première qui s'applique fixe l'issue."""
    if not eligibilite["eligible"]:
        motifs = ", ".join(eligibilite["motifs"])
        return _decision("refusee", 0.0, f"Demande non éligible : {motifs} (§4).", regle=1)

    if pieces is None or not pieces["conformes"]:
        manquantes = ", ".join(pieces["a_redemander"]) if pieces else "non vérifiées"
        return _escalade(
            "gestionnaire", f"Pièces manquantes : {manquantes}, aucun dépôt de l'assuré (§5).", 2
        )

    assert estimation is not None
    montant = float(estimation["montant_estime"])
    if montant <= 0:
        return _decision(
            "refusee", 0.0, "Dommage inférieur ou égal à la franchise de la formule (§6).", regle=3
        )

    statut_avis = (avis or {}).get("statut", "non_requis")
    mode_degrade = statut_avis == "indisponible"
    if statut_avis == "obtenu":
        if avis and avis["niveau"] == "modere":
            return _escalade(
                "gestionnaire",
                "Contrôle renforcé : risque de fraude modéré selon le partenaire.",
                4,
            )
        if avis and avis["niveau"] == "eleve":
            return _escalade(
                "cellule_fraude", "Suspicion de fraude : risque élevé selon le partenaire.", 4
            )
    elif mode_degrade and montant > regles.SEUIL_MODE_DEGRADE:
        return _escalade(
            "cellule_fraude",
            f"Contrôle anti-fraude manuel : partenaire indisponible et montant estimé "
            f"{euros(montant)} supérieur à {euros(regles.SEUIL_MODE_DEGRADE)} (§9).",
            4,
            mode_degrade=True,
        )

    if montant > regles.SEUIL_DELEGATION:
        return _escalade(
            "gestionnaire",
            f"Seuil de délégation dépassé : montant estimé {euros(montant)} supérieur à "
            f"{euros(regles.SEUIL_DELEGATION)} (§8).",
            5,
            mode_degrade=mode_degrade,
        )

    motif = f"Remboursement accordé : {euros(montant)}."
    if estimation.get("plafond_applique"):
        motif += (
            f" Plafond de la formule {estimation.get('formule', '')} atteint : aucun remboursement"
            f" ne peut dépasser {euros(estimation['plafond'])} par sinistre (§4)."
        )
    if mode_degrade:
        motif += " Décision prise sans avis anti-fraude, en mode dégradé (§9) : à contrôler."
    return _decision("acceptee", montant, motif, regle=6, mode_degrade=mode_degrade)


def escalade_interruption(motif: str, mode_degrade: bool = False) -> dict[str, Any]:
    """Issue d'une demande interrompue (borne, agent indéterminé, incident) : jamais de silence."""
    return _escalade("gestionnaire", motif, None, mode_degrade=mode_degrade)


def euros(montant: float) -> str:
    return f"{montant:,.2f} €".replace(",", " ").replace(".", ",")


def _decision(
    decision: str, montant: float, motif: str, regle: int, mode_degrade: bool = False
) -> dict[str, Any]:
    return {
        "issue": "decision",
        "decision": decision,
        "montant_rembourse": round(montant, 2),
        "motif": motif,
        "file": None,
        "mode_degrade": mode_degrade,
        "regle": regle,
    }


def _escalade(
    file: str, motif: str, regle: int | None, mode_degrade: bool = False
) -> dict[str, Any]:
    return {
        "issue": "escalade",
        "decision": None,
        "montant_rembourse": None,
        "motif": motif,
        "file": file,
        "mode_degrade": mode_degrade,
        "regle": regle,
    }
