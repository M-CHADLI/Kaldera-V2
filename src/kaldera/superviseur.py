"""Superviseur-décideur : enchaîne les agents dans un ordre fixe, fait respecter les bornes,
contrôle la forme des sorties, écrit seul l'état partagé et conclut la demande.
"""

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from typing import Any

from . import decision, espace_assure, partenaire, rapport, vues
from .agents import STATUTS, Agent, AntiFraude, Eligibilite, Estimation, Pieces, Resultat
from .bornes import BORNES
from .etat import Etat

# Clés qu'une section doit contenir pour passer le contrôle de forme.
SCHEMAS: dict[str, set[str]] = {
    "eligibilite": {"eligible", "motifs"},
    "pieces": {"conformes", "a_redemander", "factures"},
    "estimation": {"montant_justifie", "montant_estime", "plafond", "plafond_applique"},
    "avis_fraude": {"statut", "indicateurs"},
}


class BorneAtteinte(Exception):
    def __init__(self, borne: str, detail: str) -> None:
        super().__init__(f"{borne} : {detail}")
        self.borne, self.detail = borne, detail


class AgentIndetermine(Exception):
    def __init__(self, agent: str, motif: str) -> None:
        super().__init__(f"{agent} : {motif}")
        self.agent, self.motif = agent, motif


class SortieNonConforme(Exception):
    pass


class Superviseur:
    nom = "superviseur"

    def __init__(
        self,
        partenaire_url: str | None = None,
        bornes: dict[str, Any] | None = None,
        client: partenaire.ClientPartenaire | None = None,
    ) -> None:
        self.bornes = dict(bornes or BORNES)
        # Un client par lot : le registre anti-doublon et le disjoncteur sont partagés.
        self.client = client or partenaire.ClientPartenaire(
            partenaire_url,
            delai_s=self.bornes["delai_partenaire_s"],
            seuil_pannes=self.bornes["disjoncteur_echecs"],
        )
        self.eligibilite = Eligibilite()
        self.pieces = Pieces()
        self.estimation = Estimation()
        self.antifraude = AntiFraude(self._consulter_partenaire)
        self._etat: Etat | None = None

    def _consulter_partenaire(self, donnees: dict[str, Any]) -> partenaire.Consultation:
        """L'appel est pris sur le budget de la demande : jamais au-delà de duree_max_s."""
        ecoule = self._etat.ecoule_s() if self._etat else 0.0
        return self.client.consulter(donnees, delai_s=self.bornes["duree_max_s"] - ecoule - 0.5)

    # -------------------------------------------------------------- traitement

    def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
        etat = self._etat = Etat(demande)
        try:
            self._derouler(etat)
        except BorneAtteinte as borne:
            etat.arret = {"borne": borne.borne, "detail": borne.detail}
            self._conclure(
                etat,
                decision.escalade_interruption(
                    f"Traitement interrompu : borne « {borne.borne} » atteinte ({borne.detail}). "
                    "Reprise par un gestionnaire.",
                    self._mode_degrade(etat),
                ),
            )
        except AgentIndetermine as indetermine:
            self._conclure(
                etat,
                decision.escalade_interruption(
                    f"L'agent {indetermine.agent} n'a pas pu conclure : {indetermine.motif}.",
                    self._mode_degrade(etat),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — filet de sécurité : jamais de blocage silencieux
            etat.arret = {"borne": "incident", "detail": type(exc).__name__}
            self._conclure(
                etat,
                decision.escalade_interruption(
                    "Incident pendant le traitement automatisé : reprise par un gestionnaire.",
                    self._mode_degrade(etat),
                ),
            )
        return construire_fiche(etat)

    def _derouler(self, etat: Etat) -> None:
        demande = etat.demande
        eligibilite = self._executer(etat, self.eligibilite, vues.vue_eligibilite(demande))
        if not eligibilite.valeur["eligible"]:
            return self._decider(etat)  # règle 1 : arrêt immédiat

        pieces = self._boucle_pieces(etat)
        if not pieces["conformes"]:
            return self._decider(etat)  # règle 2

        estimation = self._executer(etat, self.estimation, vues.vue_estimation(demande, pieces))
        if estimation.valeur["montant_estime"] <= 0:
            return self._decider(etat)  # règle 3 : rien ne part chez le partenaire

        self._executer(etat, self.antifraude, vues.vue_antifraude(demande, estimation.valeur))
        return self._decider(etat)

    def _boucle_pieces(self, etat: Etat) -> dict[str, Any]:
        """Vérification des pièces et demandes de complément, bornées (BCL-01)."""
        demande = etat.demande
        depots: list[dict[str, Any]] = []
        sans_depot: list[str] = []
        resultat = self._executer(etat, self.pieces, vues.vue_pieces(demande, depots, sans_depot))
        complements = 0
        while resultat.statut == "complement_requis":
            if complements >= self.bornes["complements_max"]:
                raise BorneAtteinte(
                    "complements_max", f"{complements} demandes de complément sans pièce conforme"
                )
            self._verifier_bornes(etat)
            debut = perf_counter()
            connues = demande.get("pieces", []) + depots
            nouveaux, identiques = [], []
            for type_piece in resultat.valeur["a_redemander"]:
                depot = espace_assure.demander_piece(demande, type_piece, complements)
                if depot is None:
                    sans_depot.append(type_piece)
                elif self.bornes["depot_identique"] and _deja_vu(depot, connues):
                    identiques.append(type_piece)
                else:
                    nouveaux.append(depot)
            complements += 1
            etat.noter(
                self.nom,
                "demander_complement",
                [],
                (perf_counter() - debut) * 1000,
                "conclu",
                types=list(resultat.valeur["a_redemander"]),
                nouveaux_depots=len(nouveaux),
            )
            if identiques:
                raise BorneAtteinte(
                    "depot_identique",
                    f"dépôt identique à un dépôt précédent : {', '.join(identiques)}",
                )
            depots.extend(nouveaux)
            resultat = self._executer(
                etat, self.pieces, vues.vue_pieces(demande, depots, sans_depot)
            )
        return resultat.valeur

    # ------------------------------------------------------------------ agents

    def _executer(self, etat: Etat, agent: Agent, vue: dict[str, Any]) -> Resultat:
        """Appelle un agent, contrôle la forme de sa sortie, l'enregistre en son nom."""
        self._verifier_bornes(etat)
        debut = perf_counter()
        try:
            resultat = agent.traiter(vue)
            _controler_forme(agent, resultat)
        except Exception:
            etat.noter(
                agent.nom, agent.action, [], (perf_counter() - debut) * 1000, "erreur", echec=True
            )
            raise
        duree_ms = (perf_counter() - debut) * 1000
        etat.enregistrer(agent.nom, agent.section, resultat.valeur)
        etat.noter(
            agent.nom,
            agent.action,
            [agent.section],
            duree_ms,
            resultat.statut,
            echec=resultat.echec,
            appels_externes=resultat.appels_externes,
        )
        if resultat.statut == "indetermine":
            raise AgentIndetermine(agent.nom, resultat.motif or "motif non précisé")
        return resultat

    def _verifier_bornes(self, etat: Etat) -> None:
        # Une étape est toujours réservée à la conclusion : la trace ne dépasse jamais la borne.
        if len(etat.trace) + 1 >= self.bornes["etapes_max"]:
            raise BorneAtteinte("etapes_max", f"{len(etat.trace)} étapes consommées")
        if etat.ecoule_s() > self.bornes["duree_max_s"]:
            raise BorneAtteinte("duree_max_s", f"{etat.ecoule_s():.1f} s écoulées")

    # -------------------------------------------------------------- conclusion

    def _decider(self, etat: Etat) -> None:
        issue = decision.decider(
            etat.lire("eligibilite"),
            etat.lire("pieces"),
            etat.lire("estimation"),
            etat.lire("avis_fraude"),
        )
        self._conclure(etat, issue)

    def _conclure(self, etat: Etat, issue: dict[str, Any]) -> None:
        debut = perf_counter()
        etat.enregistrer(self.nom, "issue", issue)
        etat.noter(
            self.nom,
            "conclure",
            ["issue"],
            (perf_counter() - debut) * 1000,
            "conclu",
            regle=issue.get("regle"),
        )

    @staticmethod
    def _mode_degrade(etat: Etat) -> bool:
        avis = etat.lire("avis_fraude") or {}
        return avis.get("statut") == "indisponible"


def construire_fiche(etat: Etat) -> dict[str, Any]:
    """Fiche de décision (specs_metier.md, §11) + trace et arrêt (docs/interface.md)."""
    issue = etat.lire("issue")
    avis = etat.lire("avis_fraude") or {}
    avis_fiche = (
        {"niveau": avis["niveau"], "score": avis["score"]}
        if avis.get("statut") == "obtenu"
        else None
    )
    return {
        "reference": etat.reference,
        "issue": issue["issue"],
        "decision": issue["decision"],
        "montant_rembourse": issue["montant_rembourse"],
        "motif": issue["motif"],
        "file": issue["file"],
        "avis_fraude": avis_fiche,
        "mode_degrade": issue["mode_degrade"],
        "regle": issue["regle"],
        "trace": etat.trace,
        "arret": etat.arret,
        "rapport": rapport.pour_gestionnaire(etat),
        "rapport_assure": rapport.pour_assure(etat),
    }


def _controler_forme(agent: Agent, resultat: Any) -> None:
    if not isinstance(resultat, Resultat) or resultat.statut not in STATUTS:
        raise SortieNonConforme(f"{agent.nom} : sortie non conforme")
    manquantes = SCHEMAS[agent.section] - set(resultat.valeur)
    if manquantes and resultat.statut != "indetermine":
        raise SortieNonConforme(f"{agent.nom} : champs manquants {sorted(manquantes)}")


def _empreinte(piece: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(piece, sort_keys=True).encode()).hexdigest()


def _deja_vu(depot: dict[str, Any], connues: list[dict[str, Any]]) -> bool:
    """Le dépôt est-il identique à une pièce déjà reçue du même type ? (empreinte)"""
    return _empreinte(depot) in {_empreinte(p) for p in connues if p.get("type") == depot["type"]}
