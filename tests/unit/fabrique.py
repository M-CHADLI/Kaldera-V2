"""Fabrique de demandes et de faux partenaires pour les tests unitaires."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from kaldera.partenaire import Consultation

DEMANDE: dict[str, Any] = {
    "reference": "KAL-26-9001",
    "assure": {
        "id_client": "C-001",
        "nom": "Martin",
        "prenom": "Anne",
        "email": "anne.martin@example.org",
        "telephone": "0600000000",
        "iban": "FR7600000000000000000000001",
        "adresse": "1 rue de l'Exemple",
        "code_postal": "69003",
    },
    "contrat": {
        "numero": "H-0001",
        "formule": "confort",
        "date_souscription": "2021-01-15",
        "statut": "actif",
        "cotisations_a_jour": True,
    },
    "sinistre": {
        "type": "degat_des_eaux",
        "date_survenance": "2026-09-01",
        "date_declaration": "2026-09-03",
        "montant_declare": 1800.0,
        "description": "Fuite sous l'évier",
    },
    "pieces": [
        {"type": "facture", "lisible": True, "montant": 1800.0},
        {"type": "photo", "lisible": True},
    ],
    "historique": {"sinistres_12_mois": 0},
    "espace_assure": {"depots": []},
}

AVIS_FAIBLE = {
    "reference_dossier": "KAL-26-9001",
    "score": 0.12,
    "niveau": "faible",
    "indicateurs": [],
    "evaluation_id": "EVA-1",
    "version_modele": "af-2.3.1",
}


def demande(**modifs: Any) -> dict[str, Any]:
    """Une demande valide, modifiée par sections : demande(sinistre={"montant_declare": 9000})."""
    resultat = deepcopy(DEMANDE)
    for section, valeur in modifs.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(section), dict):
            resultat[section].update(valeur)
        else:
            resultat[section] = valeur
    return resultat


class FauxClient:
    """Remplace le client A2A : renvoie une consultation fixée d'avance et compte les appels."""

    def __init__(self, consultation: Consultation) -> None:
        self.consultation = consultation
        self.appels: list[dict[str, Any]] = []

    def consulter(self, donnees: dict[str, Any], delai_s: float | None = None) -> Consultation:
        self.appels.append(donnees)
        return self.consultation


VARIABLES_MODELE = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_API_VERSION",
)


def sans_modele(monkeypatch: Any) -> None:
    """Aucun modèle configuré, quelles que soient les variables de la machine (.env)."""
    for nom in VARIABLES_MODELE:
        monkeypatch.delenv(nom, raising=False)


def avec_azure_openai(monkeypatch: Any) -> None:
    sans_modele(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "cle-de-test")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://exemple.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-test")
