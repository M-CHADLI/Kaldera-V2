"""Client du service anti-fraude partenaire (A2A, JSON-RPC 2.0)."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

URL_PAR_DEFAUT = "http://localhost:8100"


def url_partenaire(url: str | None = None) -> str:
    return (url or os.environ.get("PARTENAIRE_URL") or URL_PAR_DEFAUT).rstrip("/")


def evaluer_risque(demande: dict[str, Any], url: str | None = None) -> dict[str, Any] | None:
    """Demande l'avis anti-fraude du partenaire pour une demande.

    Retourne l'évaluation du partenaire, ou ``None`` si elle n'a pas pu être obtenue.
    """
    requete = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "data", "data": demande}],
            }
        },
    }
    entetes = {"Authorization": f"Bearer {os.environ.get('PARTENAIRE_JETON', '')}"}
    try:
        reponse = httpx.post(
            f"{url_partenaire(url)}/a2a", json=requete, headers=entetes, timeout=None
        )
        reponse.raise_for_status()
        resultat = reponse.json()["result"]
        return resultat["artifacts"][0]["parts"][0]["data"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None
