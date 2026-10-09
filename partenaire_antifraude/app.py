"""Partenaire anti-fraude Kaldera — service A2A conforme au contrat v2.0 (external_agent/contrat.md).

Les routes du contrat (Agent Card, ``message/send``), plus ``/health`` proposé en v2.1, et un
journal des derniers échanges sur ``/a2a``, en lecture seule : ``GET /journal`` (même jeton)
et sa page de consultation ``GET /``. Aucune route de simulation : ce service est fait pour
être exposé.

    uvicorn partenaire_antifraude.app:app --port 8200
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, NoReturn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

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

# Journal des échanges : en mémoire seulement, borné, perdu au redémarrage.
JOURNAL_MAX_DEFAUT, JOURNAL_MAX_PLAFOND = 100, 1000
CORPS_MAX = 16_384  # octets : au-delà, un corps n'est consigné que par un extrait
EXTRAIT_MAX = 2_000  # caractères gardés d'un corps qui n'est pas consigné tel quel
PROFONDEUR_MAX = 64  # imbrication au-delà de laquelle un corps est jugé illisible
REFUS = {"detail": "jeton absent ou invalide"}
PAGE = Path(__file__).with_name("journal.html")


def taille_journal() -> int:
    """Échanges gardés : ``PARTENAIRE_JOURNAL_MAX``, ramené entre 1 et 1 000 (100 par défaut)."""
    try:
        taille = int(os.environ.get("PARTENAIRE_JOURNAL_MAX", JOURNAL_MAX_DEFAUT))
    except ValueError:
        return JOURNAL_MAX_DEFAUT
    return min(max(taille, 1), JOURNAL_MAX_PLAFOND)


app = FastAPI(title="Partenaire anti-fraude Kaldera", version="2.0")
_evalues: set[str] = set()
_verrou = threading.Lock()
_journal: deque[dict[str, Any]] = deque(maxlen=taille_journal())
_numeros = itertools.count(1)
_verrou_journal = threading.Lock()
_page = PAGE.read_text(encoding="utf-8")


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
    debut = time.perf_counter()
    if not _autorise(request):
        # Consignée sans son corps : sans jeton, personne ne remplit le journal de contenu.
        _consigner(debut, 401, {"format": "non_consigne", "motif": REFUS["detail"]}, REFUS)
        return JSONResponse(REFUS, status_code=401)
    corps = await request.body()
    reponse = _repondre(corps)
    _consigner(debut, 200, _contenu(corps), reponse)
    return reponse


@app.get("/journal")
def journal(request: Request) -> JSONResponse:
    """Derniers échanges sur ``/a2a``, plus récents en premier. Lecture seule, même jeton."""
    if not _autorise(request):
        return JSONResponse(REFUS, status_code=401)
    with _verrou_journal:
        entrees = list(reversed(_journal))
    return JSONResponse(
        {"capacite": _journal.maxlen, "nombre": len(entrees), "entrees": entrees},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def page_journal() -> HTMLResponse:
    """Page de consultation du journal ; elle n'affiche aucun échange sans le jeton."""
    return HTMLResponse(_page, headers=_entetes_page(_page))


# ------------------------------------------------------------------- logique


def _repondre(corps: bytes) -> dict[str, Any]:
    """Réponse JSON-RPC à un appel authentifié."""
    try:
        enveloppe = _lire_json(corps)
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


def _autorise(request: Request) -> bool:
    """Jeton Bearer de ``PARTENAIRE_JETON``, comparé à temps constant."""
    jeton = os.environ.get("PARTENAIRE_JETON", "")
    fourni = request.headers.get("authorization", "")
    return bool(jeton) and hmac.compare_digest(fourni.encode(), f"Bearer {jeton}".encode())


def _lire_json(brut: bytes) -> Any:
    """JSON strict : ni NaN ni Infinity, imbrication bornée ; sinon ValueError."""
    try:
        valeur = json.loads(brut, parse_constant=_refuser_constante)
    except RecursionError as exc:
        raise ValueError("imbrication trop profonde") from exc
    if _profondeur(valeur) > PROFONDEUR_MAX:
        raise ValueError("imbrication trop profonde")
    return valeur


def _refuser_constante(nom: str) -> NoReturn:
    raise ValueError(f"{nom} n'est pas du JSON")


def _profondeur(valeur: Any) -> int:
    """Profondeur d'imbrication d'une valeur JSON, calculée sans récursion."""
    pile, profondeur = [(valeur, 0)], 0
    while pile:
        v, p = pile.pop()
        profondeur = max(profondeur, p)
        if isinstance(v, dict):
            pile.extend((e, p + 1) for e in v.values())
        elif isinstance(v, list):
            pile.extend((e, p + 1) for e in v)
    return profondeur


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


# ------------------------------------------------------------------- journal


def _consigner(debut: float, statut: int, recu: dict[str, Any], envoye: dict[str, Any]) -> None:
    """Ajoute un échange au journal. Aucun en-tête, donc jamais le jeton, n'y est consigné."""
    duree_ms = round((time.perf_counter() - debut) * 1000, 2)
    entree = {
        "horodatage": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "duree_ms": duree_ms,
        "statut_http": statut,
        "resume": _resume(statut, recu, envoye),
        "recu": recu,
        "envoye": _contenu(json.dumps(envoye, ensure_ascii=False).encode()),
    }
    with _verrou_journal:
        _journal.append({"numero": next(_numeros), **entree})


def _contenu(brut: bytes) -> dict[str, Any]:
    """Corps consigné : le JSON tel quel s'il est de taille raisonnable, sinon un extrait."""
    if len(brut) <= CORPS_MAX:
        try:
            return {"format": "json", "corps": _lire_json(brut)}
        except ValueError:
            pass
    extrait = brut[: 4 * EXTRAIT_MAX].decode("utf-8", errors="replace")[:EXTRAIT_MAX]
    return {"format": "texte", "extrait": extrait, "octets": len(brut)}


def _resume(statut: int, recu: dict[str, Any], envoye: dict[str, Any]) -> dict[str, Any]:
    """L'essentiel d'un échange : méthode, dossier, puis l'avis rendu ou l'erreur."""
    corps = recu.get("corps")
    requete: dict[str, Any] = corps if isinstance(corps, dict) else {}
    donnees = _extraire(requete.get("params")) or {}
    resume = {
        "methode": _court(requete.get("method")),
        "dossier": _court(donnees.get("reference_dossier")),
    }
    if statut != 200:
        return {**resume, "issue": "refus", "message": REFUS["detail"]}
    if "error" in envoye:
        erreur = envoye["error"]
        return {**resume, "issue": "erreur", "code": erreur["code"], "message": erreur["message"]}
    evaluation = envoye["result"]["artifacts"][0]["parts"][0]["data"]
    return {
        **resume,
        "issue": "succes",
        "niveau": evaluation["niveau"],
        "score": evaluation["score"],
    }


def _court(valeur: Any) -> str | None:
    return valeur[:80] if isinstance(valeur, str) else None


def _entetes_page(page: str) -> dict[str, str]:
    """En-têtes de la page : seul son propre script s'exécute, et il n'appelle que ce service."""
    empreintes = " ".join(
        f"'sha256-{base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()}'"
        for script in re.findall(r"<script>(.*?)</script>", page, re.S)
    )
    politique = "; ".join(
        [
            "default-src 'none'",
            f"script-src {empreintes}",
            "connect-src 'self'",
            "style-src 'unsafe-inline' https://fonts.googleapis.com",
            "font-src https://fonts.gstatic.com",
            "img-src data:",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )
    return {
        "Content-Security-Policy": politique,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
