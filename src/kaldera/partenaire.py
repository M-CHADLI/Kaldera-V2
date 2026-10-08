"""Client du service anti-fraude partenaire (A2A, JSON-RPC 2.0) — external_agent/contrat.md v2.0.

- N'envoie que les 7 champs du contrat, construits champ par champ (liste blanche).
- Un seul appel par dossier, aucune relance ; abandon au plus tard après 3 s.
- Valide chaque réponse en trois couches (transport, schéma, plausibilité) avant de la croire.
- Disjoncteur par lot : après N pannes, plus aucun appel pour le reste du lot.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

URL_PAR_DEFAUT = "http://localhost:8100"

CHAMPS_REQUETE = (
    "reference_dossier",
    "type_sinistre",
    "montant_declare",
    "date_survenance",
    "anciennete_contrat_jours",
    "sinistres_12_mois",
    "departement",
)
CHAMPS_EVALUATION = {
    "reference_dossier",
    "score",
    "niveau",
    "indicateurs",
    "evaluation_id",
    "version_modele",
}
NIVEAUX = ("faible", "modere", "eleve")
INDICATEURS_PARTENAIRE = {"MONTANT_ELEVE", "SINISTRE_PRECOCE", "FREQUENCE_ELEVEE", "TYPE_SENSIBLE"}
SEUIL_MODERE, SEUIL_ELEVE = 0.40, 0.75


@dataclass(frozen=True)
class Consultation:
    """Issue d'une consultation : un avis validé, ou la raison de son absence."""

    avis: dict[str, Any] | None
    couche: str | None = None  # delai, panne, transport, schema, plausibilite, doublon, disjoncteur
    raison: str = ""
    appel_effectue: bool = True

    @property
    def panne(self) -> bool:
        return self.couche in ("delai", "panne")


class ReponseRejetee(Exception):
    def __init__(self, couche: str, raison: str) -> None:
        super().__init__(f"{couche} : {raison}")
        self.couche, self.raison = couche, raison


def url_partenaire(url: str | None = None) -> str:
    return (url or os.environ.get("PARTENAIRE_URL") or URL_PAR_DEFAUT).rstrip("/")


class ClientPartenaire:
    """Client partagé par les demandes d'un même lot : registre anti-doublon et disjoncteur."""

    def __init__(self, url: str | None = None, *, delai_s: float = 3.0, seuil_pannes: int = 2):
        self.url = url_partenaire(url)
        self.delai_s = delai_s
        self.seuil_pannes = seuil_pannes
        self._evalues: set[str] = set()
        self._pannes = 0
        self._verrou = threading.Lock()

    def consulter(self, donnees: dict[str, Any], delai_s: float | None = None) -> Consultation:
        reference = str(donnees["reference_dossier"])
        with self._verrou:
            if reference in self._evalues:
                return Consultation(
                    None, "doublon", "dossier déjà évalué : aucun second appel (contrat §6)", False
                )
            if self._pannes >= self.seuil_pannes:
                return Consultation(
                    None,
                    "disjoncteur",
                    f"partenaire en panne {self._pannes} fois dans ce lot : appel évité",
                    False,
                )
            self._evalues.add(reference)
        delai = self.delai_s if delai_s is None else max(0.1, min(self.delai_s, delai_s))
        consultation = consulter(donnees, self.url, delai)
        if consultation.panne:
            with self._verrou:
                self._pannes += 1
        return consultation


def construire_requete(donnees: dict[str, Any]) -> dict[str, Any]:
    """Message JSON-RPC ``message/send`` : les champs du contrat, et rien d'autre."""
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "data", "data": {c: donnees[c] for c in CHAMPS_REQUETE}}],
            }
        },
    }


def consulter(donnees: dict[str, Any], url: str, delai_s: float) -> Consultation:
    """Un appel, un délai ; toute réponse est validée avant d'être crue."""
    requete = construire_requete(donnees)
    entetes = {"Authorization": f"Bearer {os.environ.get('PARTENAIRE_JETON', '')}"}
    try:
        reponse = httpx.post(f"{url}/a2a", json=requete, headers=entetes, timeout=delai_s)
    except httpx.TimeoutException:
        return Consultation(None, "delai", f"aucune réponse en {delai_s:g} s")
    except httpx.HTTPError as exc:
        return Consultation(None, "panne", f"service injoignable ({type(exc).__name__})")
    if reponse.status_code >= 500:
        return Consultation(None, "panne", f"service indisponible (HTTP {reponse.status_code})")
    try:
        avis = valider_reponse(
            reponse.status_code, reponse.content, requete["id"], donnees["reference_dossier"]
        )
    except ReponseRejetee as rejet:
        return Consultation(None, rejet.couche, rejet.raison)
    return Consultation(avis)


def valider_reponse(
    statut_http: int, corps: bytes, id_requete: str, reference: str
) -> dict[str, Any]:
    """Valide une réponse en trois couches et retourne l'évaluation, réduite aux champs du contrat.

    Les messages de rejet ne recopient jamais de contenu venant du partenaire.
    """
    # Couche 1 — transport : HTTP, JSON, enveloppe JSON-RPC 2.0
    if statut_http != 200:
        raise ReponseRejetee("transport", f"statut HTTP {statut_http}")
    try:
        enveloppe = json.loads(corps)
    except ValueError as exc:
        raise ReponseRejetee("transport", "corps illisible (pas du JSON)") from exc
    if not isinstance(enveloppe, dict) or enveloppe.get("jsonrpc") != "2.0":
        raise ReponseRejetee("transport", "enveloppe JSON-RPC 2.0 invalide")
    if enveloppe.get("id") != id_requete:
        raise ReponseRejetee("transport", "identifiant JSON-RPC différent de la requête")
    if ("result" in enveloppe) == ("error" in enveloppe):
        raise ReponseRejetee(
            "transport", "enveloppe sans « result » ni « error », ou avec les deux"
        )
    if "error" in enveloppe:
        code = enveloppe["error"].get("code") if isinstance(enveloppe["error"], dict) else None
        raise ReponseRejetee("transport", f"erreur JSON-RPC {code}")

    # Couche 2 — schéma : tâche A2A terminée, une partie data, champs exacts et typés
    evaluation = _extraire_evaluation(enveloppe["result"])
    if set(evaluation) != CHAMPS_EVALUATION:
        manquants, en_trop = (
            CHAMPS_EVALUATION - set(evaluation),
            set(evaluation) - CHAMPS_EVALUATION,
        )
        raise ReponseRejetee(
            "schema", f"{len(manquants)} champ(s) manquant(s), {len(en_trop)} champ(s) hors contrat"
        )
    score = evaluation["score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ReponseRejetee("schema", "score non numérique")
    if evaluation["niveau"] not in NIVEAUX:
        raise ReponseRejetee("schema", "niveau hors des valeurs du contrat")
    indicateurs = evaluation["indicateurs"]
    if not isinstance(indicateurs, list) or not set(indicateurs) <= INDICATEURS_PARTENAIRE:
        raise ReponseRejetee("schema", "indicateurs hors des valeurs du contrat")
    if not all(
        isinstance(evaluation[c], str)
        for c in ("reference_dossier", "evaluation_id", "version_modele")
    ):
        raise ReponseRejetee("schema", "identifiants non textuels")

    # Couche 3 — plausibilité : score borné, niveau cohérent, même dossier
    if not 0 <= score <= 1:
        raise ReponseRejetee("plausibilite", "score hors de l'intervalle [0 ; 1]")
    if evaluation["niveau"] != niveau_attendu(score):
        raise ReponseRejetee("plausibilite", "niveau incohérent avec le score")
    if evaluation["reference_dossier"] != reference:
        raise ReponseRejetee("plausibilite", "évaluation portant sur un autre dossier")
    return {c: evaluation[c] for c in sorted(CHAMPS_EVALUATION)}


def _extraire_evaluation(resultat: Any) -> dict[str, Any]:
    """Tâche ``completed`` portant exactement un artefact d'exactement une partie ``data``."""
    try:
        termine = resultat["kind"] == "task" and resultat["status"]["state"] == "completed"
        (artefact,) = resultat["artifacts"]
        (partie,) = artefact["parts"]
        donnees = partie["data"] if partie["kind"] == "data" else None
    except (KeyError, TypeError, ValueError) as exc:
        raise ReponseRejetee("schema", "structure de tâche A2A non conforme") from exc
    if not termine or not isinstance(donnees, dict):
        raise ReponseRejetee("schema", "structure de tâche A2A non conforme")
    return donnees


def niveau_attendu(score: float) -> str:
    if score < SEUIL_MODERE:
        return "faible"
    return "modere" if score < SEUIL_ELEVE else "eleve"
