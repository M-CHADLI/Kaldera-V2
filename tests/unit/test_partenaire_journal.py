"""Journal des échanges de notre partenaire : ce qu'il reçoit et envoie, jamais le jeton."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import deque
from typing import Any

import pytest
from fastapi.testclient import TestClient

from partenaire_antifraude import app as partenaire

JETON = "jeton-du-journal"
ENTETES = {"Authorization": f"Bearer {JETON}"}
DONNEES = {
    "reference_dossier": "KAL-26-0042",
    "type_sinistre": "degat_des_eaux",
    "montant_declare": 1850.0,
    "date_survenance": "2026-08-14",
    "anciennete_contrat_jours": 942,
    "sinistres_12_mois": 0,
    "departement": "69",
}

client = TestClient(partenaire.app)


@pytest.fixture(autouse=True)
def contexte(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_JETON", JETON)
    partenaire._evalues.clear()
    partenaire._journal.clear()


def message(data: Any, **enveloppe: Any) -> dict[str, Any]:
    corps = {
        "jsonrpc": "2.0",
        "id": "r-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": "m-1",
                "parts": [{"kind": "data", "data": data}],
            }
        },
    }
    return {**corps, **enveloppe}


def journal() -> list[dict[str, Any]]:
    reponse = client.get("/journal", headers=ENTETES)
    assert reponse.status_code == 200
    entrees: list[dict[str, Any]] = reponse.json()["entrees"]
    return entrees


def test_un_echange_valide_est_consigne_avec_recu_et_envoye() -> None:
    envoye = client.post("/a2a", json=message(DONNEES), headers=ENTETES).json()
    (entree,) = journal()
    assert entree["statut_http"] == 200 and entree["horodatage"].endswith("Z")
    assert entree["duree_ms"] >= 0
    assert entree["recu"] == {"format": "json", "corps": message(DONNEES)}
    assert entree["envoye"] == {"format": "json", "corps": envoye}
    assert entree["resume"] == {
        "methode": "message/send",
        "dossier": "KAL-26-0042",
        "issue": "succes",
        "niveau": "faible",
        "score": 0.06,
    }


@pytest.mark.parametrize(
    ("corps", "code", "methode"),
    [
        (message({**DONNEES, "iban": "FR76"}), -32602, "message/send"),
        (message(DONNEES, method="tasks/get"), -32601, "tasks/get"),
    ],
    ids=["champ en trop", "méthode inconnue"],
)
def test_une_erreur_json_rpc_est_consignee_avec_son_code(
    corps: dict[str, Any], code: int, methode: str
) -> None:
    envoye = client.post("/a2a", json=corps, headers=ENTETES).json()
    (entree,) = journal()
    assert entree["recu"]["corps"] == corps and entree["envoye"]["corps"] == envoye
    assert entree["resume"]["issue"] == "erreur" and entree["resume"]["code"] == code
    assert (entree["resume"]["methode"], entree["resume"]["dossier"]) == (methode, "KAL-26-0042")


def test_un_doublon_est_consigne_et_les_plus_recents_viennent_en_premier() -> None:
    for _ in range(2):
        client.post("/a2a", json=message(DONNEES), headers=ENTETES)
    doublon, premier = journal()
    assert doublon["numero"] > premier["numero"]
    assert premier["resume"]["issue"] == "succes"
    assert doublon["resume"] == {
        "methode": "message/send",
        "dossier": "KAL-26-0042",
        "issue": "erreur",
        "code": -32029,
        "message": "dossier déjà évalué",
    }


def test_un_corps_illisible_est_garde_en_extrait_texte() -> None:
    client.post("/a2a", content=b"pas du json", headers=ENTETES)
    (entree,) = journal()
    assert entree["recu"] == {"format": "texte", "extrait": "pas du json", "octets": 11}
    assert entree["resume"]["code"] == -32700 and entree["resume"]["methode"] is None


def test_un_corps_trop_long_n_est_garde_qu_en_extrait() -> None:
    corps = json.dumps(message({**DONNEES, "bourrage": "x" * 20_000})).encode()
    assert client.post("/a2a", content=corps, headers=ENTETES).json()["error"]["code"] == -32602
    (entree,) = journal()
    assert entree["recu"]["format"] == "texte" and entree["recu"]["octets"] == len(corps)
    assert len(entree["recu"]["extrait"]) == partenaire.EXTRAIT_MAX


@pytest.mark.parametrize(
    "corps",
    [
        b'{"jsonrpc": "2.0", "id": NaN, "method": "message/send"}',
        json.dumps(message({**DONNEES, "montant_declare": float("inf")})).encode(),
        b"[" * 100 + b"]" * 100,
        b"[" * 5000 + b"]" * 5000,
    ],
    ids=["NaN", "montant infini", "imbrication", "récursion"],
)
def test_un_corps_hors_du_json_strict_est_illisible_et_le_journal_reste_lisible(
    corps: bytes,
) -> None:
    assert client.post("/a2a", content=corps, headers=ENTETES).json()["error"]["code"] == -32700
    (entree,) = journal()
    assert entree["recu"]["format"] == "texte" and entree["resume"]["code"] == -32700


@pytest.mark.parametrize(
    "entetes",
    [{}, {"Authorization": "Bearer jeton-pirate-123"}, {"Authorization": JETON}],
    ids=["absent", "invalide", "sans Bearer"],
)
def test_une_requete_sans_jeton_valide_est_consignee_sans_son_corps(
    entetes: dict[str, str],
) -> None:
    corps = message({**DONNEES, "commentaire": "contenu arbitraire à ne pas garder"})
    assert client.post("/a2a", json=corps, headers=entetes).status_code == 401
    (entree,) = journal()
    assert entree["statut_http"] == 401
    assert entree["recu"] == {"format": "non_consigne", "motif": "jeton absent ou invalide"}
    assert entree["envoye"]["corps"] == {"detail": "jeton absent ou invalide"}
    assert entree["resume"] == {
        "methode": None,
        "dossier": None,
        "issue": "refus",
        "message": "jeton absent ou invalide",
    }
    brut = client.get("/journal", headers=ENTETES).text
    assert "contenu arbitraire" not in brut and "KAL-26-0042" not in brut
    assert "jeton-pirate-123" not in brut and JETON not in brut


def test_le_jeton_n_apparait_jamais_dans_le_journal() -> None:
    client.post("/a2a", json=message(DONNEES), headers=ENTETES)
    client.post("/a2a", json=message(DONNEES), headers=ENTETES)
    client.post("/a2a", content=b"pas du json", headers=ENTETES)
    client.post("/a2a", json=message(DONNEES), headers={"Authorization": "Bearer faux"})
    brut = client.get("/journal", headers=ENTETES).text
    assert len(journal()) == 4
    assert JETON not in brut and "bearer" not in brut.lower()
    assert "authorization" not in brut.lower()


@pytest.mark.parametrize(
    "entetes",
    [{}, {"Authorization": "Bearer faux"}, {"Authorization": JETON}],
    ids=["absent", "invalide", "sans Bearer"],
)
def test_le_journal_exige_le_jeton(entetes: dict[str, str]) -> None:
    client.post("/a2a", json=message(DONNEES), headers=ENTETES)
    reponse = client.get("/journal", headers=entetes)
    assert reponse.status_code == 401 and "KAL-26-0042" not in reponse.text


def test_sans_jeton_configure_le_journal_reste_ferme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PARTENAIRE_JETON")
    assert client.get("/journal", headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get("/journal").status_code == 401


def test_la_lecture_du_journal_ne_se_met_pas_en_cache() -> None:
    reponse = client.get("/journal", headers=ENTETES)
    assert reponse.headers["cache-control"] == "no-store"
    assert reponse.json() == {"capacite": partenaire._journal.maxlen, "nombre": 0, "entrees": []}


def test_le_journal_est_borne(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_JOURNAL_MAX", "3")
    monkeypatch.setattr(partenaire, "_journal", deque(maxlen=partenaire.taille_journal()))
    for i in range(5):
        donnees = {**DONNEES, "reference_dossier": f"KAL-26-000{i}"}
        client.post("/a2a", json=message(donnees), headers=ENTETES)
    reponse = client.get("/journal", headers=ENTETES).json()
    assert (reponse["capacite"], reponse["nombre"]) == (3, 3)
    dossiers = [e["resume"]["dossier"] for e in reponse["entrees"]]
    assert dossiers == ["KAL-26-0004", "KAL-26-0003", "KAL-26-0002"]


@pytest.mark.parametrize(
    ("valeur", "taille"),
    [(None, 100), ("3", 3), ("0", 1), ("5000", 1000), ("beaucoup", 100), ("", 100)],
)
def test_taille_du_journal(
    monkeypatch: pytest.MonkeyPatch, valeur: str | None, taille: int
) -> None:
    if valeur is None:
        monkeypatch.delenv("PARTENAIRE_JOURNAL_MAX", raising=False)
    else:
        monkeypatch.setenv("PARTENAIRE_JOURNAL_MAX", valeur)
    assert partenaire.taille_journal() == taille


def test_la_page_est_servie_sans_jeton_avec_une_politique_de_securite() -> None:
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("text/html")
    page = reponse.text
    assert '<label for="jeton">' in page and "sessionStorage" in page and JETON not in page
    (script,) = re.findall(r"<script>(.*?)</script>", page, re.S)
    empreinte = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    politique = reponse.headers["content-security-policy"]
    assert f"script-src 'sha256-{empreinte}'" in politique
    assert "connect-src 'self'" in politique and "frame-ancestors 'none'" in politique


@pytest.mark.parametrize(
    ("methode", "route", "statut"),
    [
        ("GET", "/_sim/etat", 404),
        ("POST", "/_sim/reset", 404),
        ("POST", "/journal", 405),
        ("DELETE", "/journal", 405),
    ],
)
def test_aucune_route_de_simulation_ni_d_ecriture(methode: str, route: str, statut: int) -> None:
    assert client.request(methode, route, headers=ENTETES).status_code == statut
