"""Partenaire anti-fraude Kaldera — service A2A conforme au contrat v2.0 (external_agent/contrat.md).

Uniquement les routes du contrat (Agent Card, ``message/send``), plus ``/health`` proposé en
v2.1. Aucune route de simulation : ce service est fait pour être exposé.

    uvicorn partenaire_antifraude.app:app --port 8200
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import date
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

VERSION_MODELE = "kaldera-af-1.0.0"
TYPES_SINISTRE = ("degat_des_eaux", "incendie", "bris_de_glace", "vol")
REFERENCE = re.compile(r"^KAL-\d{2}-\d{4}$")
DEPARTEMENT = re.compile(r"^(\d{2}|2A|2B|9[78]\d)$")

# Règles de score (mêmes poids que le partenaire de référence, pour rester cohérent avec les
# scénarios de recette). Chaque règle : indicateur, condition, poids.
REGLES = (
    ("MONTANT_ELEVE", lambda d: d["montant_declare"] >= 5000, 0.22),
    ("SINISTRE_PRECOCE", lambda d: d["anciennete_contrat_jours"] < 90, 0.18),
    ("FREQUENCE_ELEVEE", lambda d: d["sinistres_12_mois"] >= 3, 0.30),
    ("TYPE_SENSIBLE", lambda d: d["type_sinistre"] == "vol", 0.12),
)
SCORE_DE_BASE, SCORE_MAX = 0.06, 0.97

app = FastAPI(title="Partenaire anti-fraude Kaldera", version="2.0")
_evalues: set[str] = set()
_verrou = threading.Lock()


# ------------------------------------------------------------------- routes


@app.get("/.well-known/agent.json")
def agent_card(request: Request) -> dict[str, Any]:
    url = os.environ.get("URL_PUBLIQUE") or str(request.base_url).rstrip("/")
    return {
        "name": "Partenaire anti-fraude Kaldera",
        "description": "Avis consultatif sur le risque de fraude d'un dossier de sinistre.",
        "url": f"{url}/a2a",
        "version": "2.0",
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "securitySchemes": {"jeton": {"type": "http", "scheme": "bearer"}},
        "security": [{"jeton": []}],
        "skills": [
            {
                "id": "evaluer_risque",
                "name": "Évaluer le risque de fraude",
                "description": "Score entre 0 et 1, niveau faible, modere ou eleve.",
                "tags": ["assurance", "fraude"],
            }
        ],
    }


@app.get("/health")
def sante() -> dict[str, str]:
    return {"statut": "ok", "version_modele": VERSION_MODELE}


@app.post("/a2a")
async def a2a(request: Request) -> Any:
    jeton = os.environ.get("PARTENAIRE_JETON", "")
    if not jeton or request.headers.get("authorization") != f"Bearer {jeton}":
        return JSONResponse({"detail": "jeton absent ou invalide"}, status_code=401)
    try:
        enveloppe = json.loads(await request.body())
    except ValueError:
        return _erreur(None, -32700, "corps illisible")
    if (
        not isinstance(enveloppe, dict)
        or enveloppe.get("jsonrpc") != "2.0"
        or not isinstance(enveloppe.get("id"), (str, int))
        or not isinstance(enveloppe.get("method"), str)
    ):
        return _erreur(
            enveloppe.get("id") if isinstance(enveloppe, dict) else None,
            -32600,
            "enveloppe invalide",
        )
    id_rpc = enveloppe["id"]
    if enveloppe["method"] != "message/send":
        return _erreur(id_rpc, -32601, "méthode inconnue")
    donnees = _extraire(enveloppe.get("params"))
    if donnees is None:
        return _erreur(id_rpc, -32602, "le message doit contenir exactement une partie data")
    problemes = valider(donnees)
    if any(problemes.values()):
        return _erreur(id_rpc, -32602, "données non conformes", problemes)
    with _verrou:
        if donnees["reference_dossier"] in _evalues:
            return _erreur(
                id_rpc, -32029, "dossier déjà évalué", {"reference": donnees["reference_dossier"]}
            )
        _evalues.add(donnees["reference_dossier"])
    return _tache(id_rpc, evaluer(donnees))


# ------------------------------------------------------------------- logique


def evaluer(donnees: dict[str, Any]) -> dict[str, Any]:
    """Évaluation déterministe et explicable : chaque indicateur relevé ajoute son poids."""
    indicateurs = [nom for nom, condition, _ in REGLES if condition(donnees)]
    poids = sum(p for nom, _, p in REGLES if nom in indicateurs)
    score = round(min(SCORE_DE_BASE + poids, SCORE_MAX), 2)
    niveau = "faible" if score < 0.40 else "modere" if score < 0.75 else "eleve"
    empreinte = hashlib.sha1(donnees["reference_dossier"].encode()).hexdigest()[:10]
    return {
        "reference_dossier": donnees["reference_dossier"],
        "score": score,
        "niveau": niveau,
        "indicateurs": indicateurs,
        "evaluation_id": f"EVA-{empreinte}",
        "version_modele": VERSION_MODELE,
    }


def valider(donnees: dict[str, Any]) -> dict[str, list[str]]:
    """Schéma strict du contrat : les 7 champs, tous obligatoires, aucun autre."""
    attendus = {
        "reference_dossier": lambda v: isinstance(v, str) and bool(REFERENCE.match(v)),
        "type_sinistre": lambda v: v in TYPES_SINISTRE,
        "montant_declare": lambda v: _nombre(v) and v > 0,
        "date_survenance": _date,
        "anciennete_contrat_jours": lambda v: _entier(v) and v >= 0,
        "sinistres_12_mois": lambda v: _entier(v) and v >= 0,
        "departement": lambda v: isinstance(v, str) and bool(DEPARTEMENT.match(v)),
    }
    return {
        "champs_inconnus": sorted(set(donnees) - set(attendus)),
        "champs_absents": sorted(set(attendus) - set(donnees)),
        "champs_invalides": sorted(
            c for c, ok in attendus.items() if c in donnees and not ok(donnees[c])
        ),
    }


def _extraire(params: Any) -> dict[str, Any] | None:
    try:
        (partie,) = params["message"]["parts"]
        if partie["kind"] == "data" and isinstance(partie["data"], dict):
            return dict(partie["data"])
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _tache(id_rpc: Any, evaluation: dict[str, Any]) -> dict[str, Any]:
    suffixe = uuid.uuid4().hex[:8]
    return {
        "jsonrpc": "2.0",
        "id": id_rpc,
        "result": {
            "kind": "task",
            "id": f"tsk-{suffixe}",
            "status": {"state": "completed"},
            "artifacts": [
                {"artifactId": f"art-{suffixe}", "parts": [{"kind": "data", "data": evaluation}]}
            ],
        },
    }


def _erreur(id_rpc: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    erreur: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        erreur["data"] = data
    return {"jsonrpc": "2.0", "id": id_rpc, "error": erreur}


def _nombre(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _entier(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _date(v: Any) -> bool:
    try:
        return isinstance(v, str) and date.fromisoformat(v).isoformat() == v
    except ValueError:
        return False
