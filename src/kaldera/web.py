"""Console web Kaldera : rejouer les scénarios, piloter le partenaire simulé, lire les rapports.

    uv run uvicorn kaldera.web:app --port 8000      (ou : make web)

Le pilotage du partenaire passe par les routes ``/_sim/*`` du banc de simulation : il ne
fonctionne qu'avec le partenaire simulé (external_agent), jamais avec le service réel.
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from . import bornes, traiter_demande, traiter_lot
from .partenaire import url_partenaire

RACINE = Path(__file__).resolve().parents[2]
PAGE = Path(__file__).with_name("console.html")
MODES = ("scenario", "normal", "lent", "invalide", "panne")
RUBRIQUES = ("reference", "assure", "contrat", "sinistre")

app = FastAPI(title="Kaldera V2 · console", version="0.4.0")


@lru_cache(maxsize=1)
def scenarios() -> dict[str, dict[str, Any]]:
    chemin = Path(os.environ.get("KALDERA_SCENARIOS", RACINE / "eval" / "scenarios.jsonl"))
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    return {s["id"]: s for s in (json.loads(ligne) for ligne in lignes if ligne.strip())}


def regler_partenaire(reglage: dict[str, Any]) -> None:
    """Remet à zéro le partenaire simulé et lui applique un comportement."""
    with httpx.Client(base_url=url_partenaire(), timeout=3.0) as client:
        client.post("/_sim/reset").raise_for_status()
        client.post("/_sim/mode", json=reglage).raise_for_status()


@app.get("/", response_class=HTMLResponse)
def console() -> str:
    return PAGE.read_text(encoding="utf-8")


@app.get("/api/scenarios")
def lister_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "id": s["id"],
            "categorie": s["categorie"],
            "titre": s["titre"],
            "partenaire": s["partenaire"],
            "demandes": len(s["demandes"]),
        }
        for s in scenarios().values()
    ]


@app.get("/api/bornes")
def lire_bornes() -> dict[str, Any]:
    return bornes()


@app.get("/api/sante")
def sante() -> dict[str, Any]:
    try:
        httpx.get(f"{url_partenaire()}/_sim/etat", timeout=1.0).raise_for_status()
        partenaire = "en ligne"
    except httpx.HTTPError:
        partenaire = "injoignable"
    return {"kaldera": "ok", "partenaire": partenaire, "url_partenaire": url_partenaire()}


@app.post("/api/scenarios/{identifiant}/rejouer")
def rejouer(identifiant: str, mode: str = "scenario") -> dict[str, Any]:
    scenario = scenarios().get(identifiant)
    if scenario is None:
        raise HTTPException(404, f"scénario inconnu : {identifiant}")
    if mode not in MODES:
        raise HTTPException(422, f"mode inconnu : {mode} (attendu : {', '.join(MODES)})")
    reglage = scenario["partenaire"] if mode == "scenario" else {"mode": mode}
    try:
        regler_partenaire(reglage)
    except httpx.HTTPError as exc:
        raise HTTPException(
            502, "Partenaire simulé injoignable : lancez « make partenaire » ou « make up »."
        ) from exc
    debut = time.perf_counter()
    resultat = traiter_lot(scenario["demandes"])
    return {
        "scenario": {k: scenario[k] for k in ("id", "categorie", "titre")},
        "reglage": reglage,
        "duree_s": round(time.perf_counter() - debut, 2),
        "fiches": resultat["fiches"],
        "attendus": scenario["attendu"],
        "conformes": [
            conforme(f, a) for f, a in zip(resultat["fiches"], scenario["attendu"], strict=True)
        ],
        "metriques": resultat["metriques"],
    }


@app.post("/api/demandes")
def soumettre(demande: dict[str, Any] = Body(...)) -> dict[str, Any]:
    manquantes = [r for r in RUBRIQUES if r not in demande]
    if manquantes:
        raise HTTPException(422, f"demande mal formée : rubriques absentes {manquantes}")
    # Toute autre anomalie donne une escalade motivée, jamais une erreur silencieuse (E1).
    return traiter_demande(demande)


def conforme(fiche: dict[str, Any], attendu: dict[str, Any]) -> bool:
    """La fiche correspond-elle à l'issue attendue par le scénario ?"""
    for champ in ("issue", "decision", "file", "mode_degrade"):
        if champ in attendu and fiche.get(champ) != attendu[champ]:
            return False
    if attendu.get("montant_rembourse") is not None:
        if abs((fiche.get("montant_rembourse") or 0) - attendu["montant_rembourse"]) >= 0.01:
            return False
    if "avis_fraude" in attendu:
        if (fiche.get("avis_fraude") or {}).get("niveau") != attendu["avis_fraude"]:
            return False
    return not (attendu.get("arret") and not fiche.get("arret"))
