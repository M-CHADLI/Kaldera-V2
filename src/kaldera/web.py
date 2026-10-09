"""Console web Kaldera : rejouer les scénarios, piloter le partenaire simulé, lire les rapports.

    uv run uvicorn kaldera.web:app --port 8000      (ou : make web)

La console détecte le partenaire branché sur ``PARTENAIRE_URL`` :

- **simulé** (external_agent) : il expose le banc ``/_sim/*``, que la console utilise pour le
  remettre à zéro et lui imposer un comportement avant chaque rejeu ;
- **réel** (partenaire_antifraude, Cloud Run) : il n'expose que les routes du contrat. Aucun
  réglage n'est tenté ; seul le rejeu tel que prévu par le scénario est permis, et un second
  rejeu du même scénario déclenche le doublon (-32029), donc le mode dégradé.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import bornes, extraction, traiter_demande, traiter_lot
from .partenaire import url_partenaire

RACINE = Path(__file__).resolve().parents[2]
PAGE = Path(__file__).with_name("console.html")
MODES = ("scenario", "normal", "lent", "invalide", "panne")
RUBRIQUES = ("reference", "assure", "contrat", "sinistre")
# Sondes de détection : le banc de simulation, puis les routes du contrat (/health en v2.1).
SONDE_SIMULATION = "/_sim/etat"
SONDES_CONTRAT = ("/health", "/.well-known/agent.json")
DELAI_SONDE_S = 3.0  # laisse le temps à un service Cloud Run de sortir de veille

TypePartenaire = Literal["simulé", "réel"]

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


def _sonder(url: str) -> int | None:
    """Code HTTP renvoyé par ``url``, ou None si personne ne répond."""
    try:
        return httpx.get(url, timeout=DELAI_SONDE_S).status_code
    except httpx.HTTPError:
        return None


def type_partenaire() -> TypePartenaire | None:
    """Type du partenaire branché sur ``PARTENAIRE_URL`` ; None s'il est injoignable.

    Simulé s'il expose le banc ``/_sim/etat`` ; réel s'il répond sur ``/health`` ou sur son
    Agent Card. Un hôte muet dès la première sonde n'est pas interrogé davantage.
    """
    base = url_partenaire()
    statut = _sonder(f"{base}{SONDE_SIMULATION}")
    if statut is None:
        return None
    if statut == 200:
        return "simulé"
    if any(_sonder(f"{base}{route}") == 200 for route in SONDES_CONTRAT):
        return "réel"
    return None


def preparer_partenaire(
    type_: TypePartenaire | None, scenario: dict[str, Any], mode: str
) -> dict[str, Any] | None:
    """Prépare le partenaire avant un rejeu ; renvoie le réglage appliqué (None : aucun)."""
    if type_ is None:
        raise HTTPException(
            502,
            f"Partenaire injoignable ({url_partenaire()}) : lancez « make partenaire » "
            "ou « make up », ou vérifiez PARTENAIRE_URL.",
        )
    if type_ == "réel":
        # Le service réel n'a pas de banc /_sim : rien à régler, rien à remettre à zéro.
        if mode != "scenario":
            raise HTTPException(
                409,
                f"Partenaire réel : impossible de forcer le mode « {mode} » sur le service "
                "réel. Rejouez avec le comportement prévu par le scénario.",
            )
        return None
    reglage: dict[str, Any] = scenario["partenaire"] if mode == "scenario" else {"mode": mode}
    try:
        regler_partenaire(reglage)
    except httpx.HTTPError as exc:
        raise HTTPException(
            502, "Partenaire simulé injoignable : lancez « make partenaire » ou « make up »."
        ) from exc
    return reglage


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
    type_ = type_partenaire()
    return {
        "kaldera": "ok",
        "partenaire": "injoignable" if type_ is None else "en ligne",
        "type": type_,
        "url_partenaire": url_partenaire(),
    }


@app.post("/api/scenarios/{identifiant}/rejouer")
def rejouer(identifiant: str, mode: str = "scenario") -> dict[str, Any]:
    scenario = scenarios().get(identifiant)
    if scenario is None:
        raise HTTPException(404, f"scénario inconnu : {identifiant}")
    if mode not in MODES:
        raise HTTPException(422, f"mode inconnu : {mode} (attendu : {', '.join(MODES)})")
    type_ = type_partenaire()
    reglage = preparer_partenaire(type_, scenario, mode)
    debut = time.perf_counter()
    resultat = traiter_lot(scenario["demandes"])
    return {
        "scenario": {k: scenario[k] for k in ("id", "categorie", "titre")},
        "type_partenaire": type_,
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


@app.post("/api/analyse")
async def analyser_dossier(request: Request) -> dict[str, Any]:
    """Analyse un dossier PDF (corps de la requête = le PDF) : demande extraite et fiche à valider.

    Rien n'est conservé : ni le PDF, ni son texte. L'utilisateur valide la demande, puis la
    soumet à ``/api/demandes``.
    """
    declare = request.headers.get("content-length")
    if declare and declare.isdigit() and int(declare) > extraction.TAILLE_MAX_OCTETS:
        raise HTTPException(413, "fichier trop volumineux")
    corps = bytearray()
    async for morceau in request.stream():
        corps += morceau
        if len(corps) > extraction.TAILLE_MAX_OCTETS:
            raise HTTPException(413, "fichier trop volumineux")
    try:
        return extraction.analyser(bytes(corps)).en_dict()
    except extraction.PdfInvalide as exc:
        raise HTTPException(422, str(exc)) from exc
    except extraction.ExtractionIndisponible as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/analyse-dossier")
async def analyser_pieces(request: Request) -> dict[str, Any]:
    """Analyse les pièces importées une à une : ``{"documents": [{"role", "nom", "contenu"}]}``.

    ``contenu`` est le fichier en base64 ; ``role`` vaut contrat, declaration, dossier, facture,
    plainte ou photo. Rien n'est conservé.
    """
    limite = extraction.TAILLE_TOTALE_MAX_OCTETS * 4 // 3 + 4096
    corps = bytearray()
    async for morceau in request.stream():
        corps += morceau
        if len(corps) > limite:
            raise HTTPException(413, "dossier trop volumineux")
    try:
        entrees = json.loads(corps)["documents"]
        documents = [
            extraction.Document(
                str(e["role"]),
                str(e.get("nom") or e["role"]),
                base64.b64decode(e["contenu"], validate=True),
            )
            for e in entrees
        ]
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise HTTPException(
            422, "requête mal formée : documents attendus avec role, nom et contenu en base64"
        ) from exc
    try:
        return extraction.analyser_documents(documents).en_dict()
    except extraction.PdfInvalide as exc:
        raise HTTPException(422, str(exc)) from exc
    except extraction.ExtractionIndisponible as exc:
        raise HTTPException(503, str(exc)) from exc


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
