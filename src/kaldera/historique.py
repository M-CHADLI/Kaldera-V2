"""Historique neutralisé des demandes traitées (docs/conception/2-orchestration-memoire.md).

Une ligne JSON par demande, construite par **liste blanche** : seuls les champs nommés ici
sont recopiés, `id_client` est pseudonymisé par HMAC, le texte libre n'est jamais stocké.
Activé seulement si `KALDERA_HISTORIQUE` donne le chemin d'un fichier JSONL ; sinon, rien.
Une erreur d'écriture ne casse jamais le traitement : elle est journalisée puis ignorée.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

VARIABLE_CHEMIN = "KALDERA_HISTORIQUE"
VARIABLE_CLE = "KALDERA_CLE_HMAC"
LONGUEUR_PSEUDONYME = 16

# Champs de la fiche conservés. Jamais `rapport_assure` ni rien qui vienne de la demande :
# nom, coordonnées, IBAN, adresse, numéro de contrat, description, pièces.
CHAMPS_FICHE = (
    "issue",
    "decision",
    "montant_rembourse",
    "file",
    "motif",
    "mode_degrade",
    "regle",
    "avis_fraude",
    "arret",
    "rapport",
)
# Champs d'une étape de trace conservés ; les détails propres à une étape sont écartés.
CHAMPS_TRACE = ("agent", "action", "ecrit", "statut", "duree_ms", "regle", "revue")

_journal = logging.getLogger(__name__)
# Les lots sont traités en parallèle par threads : une écriture à la fois dans le fichier.
_verrou = threading.Lock()


def pseudonymiser(id_client: Any, cle: str | None) -> str | None:
    """HMAC-SHA256 de l'identifiant client, en hexadécimal tronqué.

    Sans clé (ou sans identifiant), retourne None : ni identifiant en clair, ni hachage sans
    clé, qu'un simple dictionnaire des identifiants suffirait à inverser.
    """
    if not cle or id_client is None or id_client == "":
        return None
    empreinte = hmac.new(cle.encode("utf-8"), str(id_client).encode("utf-8"), hashlib.sha256)
    return empreinte.hexdigest()[:LONGUEUR_PSEUDONYME]


def neutraliser(
    demande: dict[str, Any],
    fiche: dict[str, Any],
    *,
    cle: str | None = None,
    maintenant: datetime | None = None,
) -> dict[str, Any]:
    """Ligne d'historique d'une demande : seuls les champs de la liste blanche y figurent."""
    assure = demande.get("assure")
    id_client = assure.get("id_client") if isinstance(assure, dict) else None
    ligne: dict[str, Any] = {
        "horodatage": (maintenant or datetime.now(UTC)).isoformat(timespec="milliseconds"),
        "reference": fiche.get("reference", demande.get("reference")),
        "client": pseudonymiser(id_client, cle),
    }
    ligne.update({champ: fiche.get(champ) for champ in CHAMPS_FICHE})
    ligne["trace"] = [
        {champ: etape[champ] for champ in CHAMPS_TRACE if champ in etape}
        for etape in fiche.get("trace") or []
    ]
    return ligne


def enregistrer(demande: dict[str, Any], fiche: dict[str, Any]) -> None:
    """Ajoute à l'historique la ligne neutralisée de la demande, s'il est activé."""
    chemin = os.environ.get(VARIABLE_CHEMIN)
    if not chemin:
        return
    try:
        ligne = neutraliser(demande, fiche, cle=os.environ.get(VARIABLE_CLE) or None)
        texte = json.dumps(ligne, ensure_ascii=False) + "\n"
        with _verrou, open(chemin, "a", encoding="utf-8") as fichier:
            fichier.write(texte)
    except Exception as exc:  # noqa: BLE001 — l'historique ne bloque jamais une demande
        _journal.warning(
            "Historique : ligne non écrite pour la demande %s (%s : %s)",
            fiche.get("reference"),
            type(exc).__name__,
            exc,
        )
