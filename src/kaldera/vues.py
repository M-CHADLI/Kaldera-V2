"""Vues des agents : chacun ne reçoit que ce dont il a besoin (moindre privilège)."""

from __future__ import annotations

from typing import Any

from . import regles


def vue_eligibilite(demande: dict[str, Any]) -> dict[str, Any]:
    contrat, sinistre = demande["contrat"], demande["sinistre"]
    return {
        "statut_contrat": contrat["statut"],
        "cotisations_a_jour": contrat["cotisations_a_jour"],
        "formule": contrat["formule"],
        "date_souscription": contrat["date_souscription"],
        "type_sinistre": sinistre["type"],
        "date_survenance": sinistre["date_survenance"],
        "date_declaration": sinistre["date_declaration"],
    }


def vue_pieces(
    demande: dict[str, Any], depots: list[dict[str, Any]], sans_depot: list[str]
) -> dict[str, Any]:
    return {
        "type_sinistre": demande["sinistre"]["type"],
        "pieces": [dict(p) for p in demande.get("pieces", [])] + [dict(d) for d in depots],
        "sans_depot": list(sans_depot),
    }


def vue_estimation(demande: dict[str, Any], pieces: dict[str, Any]) -> dict[str, Any]:
    formule = demande["contrat"]["formule"]
    return {
        "formule": formule,
        "montant_declare": float(demande["sinistre"]["montant_declare"]),
        "factures": list(pieces["factures"]),
        "franchise": regles.FORMULES[formule]["franchise"],
        "plafond": regles.FORMULES[formule]["plafond"],
    }


def vue_antifraude(demande: dict[str, Any], estimation: dict[str, Any]) -> dict[str, Any]:
    """Les champs du contrat partenaire, plus le montant justifié (pour F4, ne part jamais)."""
    return {
        "donnees_contrat": champs_contrat(demande),
        "montant_justifie": estimation["montant_justifie"],
    }


def champs_contrat(demande: dict[str, Any]) -> dict[str, Any]:
    """Les 7 champs autorisés par external_agent/contrat.md, et rien d'autre."""
    contrat, sinistre = demande["contrat"], demande["sinistre"]
    return {
        "reference_dossier": demande["reference"],
        "type_sinistre": sinistre["type"],
        "montant_declare": float(sinistre["montant_declare"]),
        "date_survenance": sinistre["date_survenance"],
        "anciennete_contrat_jours": regles.jours_entre(
            contrat["date_souscription"], sinistre["date_survenance"]
        ),
        "sinistres_12_mois": int(demande.get("historique", {}).get("sinistres_12_mois", 0)),
        "departement": departement(demande["assure"]["code_postal"]),
    }


def departement(code_postal: str) -> str:
    """Département au sens du contrat : 2 caractères, 2A/2B en Corse, 3 chiffres outre-mer."""
    code = str(code_postal).strip()
    if code.startswith("20"):
        return "2A" if int(code[:3]) < 202 else "2B"
    if code[:2] in ("97", "98"):
        return code[:3]
    return code[:2]
