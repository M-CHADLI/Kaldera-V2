"""Agent de traitement des demandes de remboursement."""

from __future__ import annotations

from typing import Any

from . import espace_assure, partenaire, regles


class AgentGeneraliste:
    """Mène l'ensemble des contrôles d'une demande, action par action."""

    nom = "generaliste"

    def __init__(self, partenaire_url: str | None = None) -> None:
        self.partenaire_url = partenaire_url

    # ------------------------------------------------------------------ routage

    def prochaine_action(self, etat: dict[str, Any]) -> str | None:
        if "issue" in etat or etat.get("attente_partenaire"):
            return None
        if "eligibilite" not in etat:
            return "verifier_eligibilite"
        if not etat["eligibilite"]["eligible"]:
            return "conclure"
        pieces = etat.get("pieces")
        if pieces is None or pieces["a_verifier"]:
            return "verifier_pieces"
        if pieces["a_redemander"] and not pieces["sans_depot"]:
            return "demander_complement"
        if not pieces["conformes"]:
            return "conclure"
        if "estimation" not in etat:
            return "estimer"
        if self._controle_requis(etat) and "avis_fraude" not in etat:
            return "consulter_partenaire"
        return "conclure"

    def executer(self, action: str, etat: dict[str, Any]) -> list[str]:
        """Exécute une action et retourne les sections de l'état qu'elle a écrites."""
        return getattr(self, action)(etat)

    # ----------------------------------------------------------------- actions

    def verifier_eligibilite(self, etat: dict[str, Any]) -> list[str]:
        demande = etat["demande"]
        contrat, sinistre = demande["contrat"], demande["sinistre"]
        formule = regles.FORMULES[contrat["formule"]]
        motifs = []
        if contrat["statut"] != "actif":
            motifs.append("contrat non actif")
        if not contrat["cotisations_a_jour"]:
            motifs.append("cotisations impayées")
        if (
            regles.jours_entre(contrat["date_souscription"], sinistre["date_survenance"])
            < regles.CARENCE_JOURS
        ):
            motifs.append("sinistre survenu pendant la période de carence")
        delai = regles.jours_entre(sinistre["date_survenance"], sinistre["date_declaration"])
        delai_max = (
            regles.DELAI_DECLARATION_VOL_JOURS
            if sinistre["type"] == "vol"
            else regles.DELAI_DECLARATION_JOURS
        )
        if delai > delai_max:
            motifs.append("déclaration hors délai")
        if sinistre["type"] not in formule["garanties"]:
            motifs.append("sinistre non couvert par la formule")
        if sinistre["montant_declare"] > formule["plafond"]:
            motifs.append("montant supérieur au plafond de garantie")
        etat["eligibilite"] = {"eligible": not motifs, "motifs": motifs}
        return ["eligibilite"]

    def verifier_pieces(self, etat: dict[str, Any]) -> list[str]:
        demande = etat["demande"]
        precedent = etat.get("pieces", {})
        recues = list(demande.get("pieces", [])) + etat.get("depots", [])
        a_redemander = []
        for type_piece in regles.PIECES_EXIGEES[demande["sinistre"]["type"]]:
            du_type = [p for p in recues if p["type"] == type_piece]
            if not du_type or not du_type[-1].get("lisible", False):
                a_redemander.append(type_piece)
        etat["pieces"] = {
            "conformes": not a_redemander,
            "a_redemander": a_redemander,
            "a_verifier": False,
            "sans_depot": precedent.get("sans_depot", False),
            "factures": [
                p["montant"] for p in recues if p["type"] == "facture" and p.get("lisible", False)
            ],
        }
        return ["pieces"]

    def demander_complement(self, etat: dict[str, Any]) -> list[str]:
        pieces = etat["pieces"]
        tentatives = etat.setdefault("tentatives", {})
        for type_piece in pieces["a_redemander"]:
            depot = espace_assure.demander_piece(
                etat["demande"], type_piece, tentatives.get(type_piece, 0)
            )
            tentatives[type_piece] = tentatives.get(type_piece, 0) + 1
            if depot is None:
                pieces["sans_depot"] = True
            else:
                etat.setdefault("depots", []).append(depot)
                pieces["a_verifier"] = True
        return ["pieces"]

    def estimer(self, etat: dict[str, Any]) -> list[str]:
        demande = etat["demande"]
        formule = regles.FORMULES[demande["contrat"]["formule"]]
        justifie = round(sum(etat["pieces"]["factures"]), 2)
        retenu = min(demande["sinistre"]["montant_declare"], justifie)
        etat["estimation"] = {
            "montant_justifie": justifie,
            "montant_estime": round(max(0.0, retenu - formule["franchise"]), 2),
        }
        return ["estimation"]

    def consulter_partenaire(self, etat: dict[str, Any]) -> list[str]:
        avis = partenaire.evaluer_risque(etat["demande"], self.partenaire_url)
        if avis is None:
            etat["attente_partenaire"] = True
            return []
        etat["avis_fraude"] = avis
        return ["avis_fraude"]

    def conclure(self, etat: dict[str, Any]) -> list[str]:
        etat["issue"] = self._issue(etat)
        return ["issue"]

    # ------------------------------------------------------------------ règles

    def _controle_requis(self, etat: dict[str, Any]) -> bool:
        demande = etat["demande"]
        sinistre = demande["sinistre"]
        anciennete = regles.jours_entre(
            demande["contrat"]["date_souscription"], sinistre["date_survenance"]
        )
        justifie = etat["estimation"]["montant_justifie"]
        return (
            sinistre["montant_declare"] >= regles.SEUIL_MONTANT_FRAUDE
            or anciennete < regles.ANCIENNETE_SENSIBLE_JOURS
            or demande.get("historique", {}).get("sinistres_12_mois", 0)
            >= regles.FREQUENCE_SENSIBLE
            or sinistre["montant_declare"] > justifie * (1 + regles.ECART_DECLARATION_MAX)
        )

    def _issue(self, etat: dict[str, Any]) -> dict[str, Any]:
        if not etat["eligibilite"]["eligible"]:
            return _decision(
                "refusee", 0.0, "Demande non éligible : " + ", ".join(etat["eligibilite"]["motifs"])
            )
        if not etat["pieces"]["conformes"]:
            manquantes = ", ".join(etat["pieces"]["a_redemander"])
            return _escalade("gestionnaire", f"Pièces manquantes : {manquantes}")
        montant = etat["estimation"]["montant_estime"]
        if montant <= 0:
            return _decision("refusee", 0.0, "Dommage inférieur ou égal à la franchise")
        avis = etat.get("avis_fraude")
        if avis is not None:
            if avis.get("niveau") == "modere":
                return _escalade("gestionnaire", "Contrôle renforcé : risque de fraude modéré")
            if avis.get("niveau") == "eleve":
                return _escalade("cellule_fraude", "Suspicion de fraude")
        if montant > regles.SEUIL_DELEGATION:
            return _escalade("gestionnaire", "Seuil de délégation dépassé")
        return _decision("acceptee", montant, f"Remboursement accordé : {montant:.2f} €")


def _decision(decision: str, montant: float, motif: str) -> dict[str, Any]:
    return {
        "issue": "decision",
        "decision": decision,
        "montant_rembourse": montant,
        "motif": motif,
        "file": None,
    }


def _escalade(file: str, motif: str) -> dict[str, Any]:
    return {
        "issue": "escalade",
        "decision": None,
        "montant_rembourse": None,
        "motif": motif,
        "file": file,
    }
