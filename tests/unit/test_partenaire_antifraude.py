"""Notre partenaire anti-fraude : conformité au contrat v2.0, et dialogue réel avec Kaldera."""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient

import kaldera
from partenaire_antifraude import app as partenaire

from fabrique import demande

JETON = "jeton-de-test"
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


@pytest.fixture(autouse=True)
def contexte(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_JETON", JETON)
    partenaire._evalues.clear()


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


client = TestClient(partenaire.app)


def test_agent_card_et_sante() -> None:
    carte = client.get("/.well-known/agent.json").json()
    assert carte["url"].endswith("/a2a") and carte["skills"][0]["id"] == "evaluer_risque"
    assert client.get("/health").json()["statut"] == "ok"


def test_une_requete_conforme_recoit_une_tache_terminee() -> None:
    reponse = client.post("/a2a", json=message(DONNEES), headers=ENTETES).json()
    evaluation = reponse["result"]["artifacts"][0]["parts"][0]["data"]
    assert reponse["id"] == "r-1" and reponse["result"]["status"]["state"] == "completed"
    assert (evaluation["score"], evaluation["niveau"]) == (0.06, "faible")


@pytest.mark.parametrize(
    ("corps", "code"),
    [
        (b"pas du json", -32700),
        (json.dumps({"jsonrpc": "1.0", "id": 1, "method": "message/send"}).encode(), -32600),
        (json.dumps(message(DONNEES, method="tasks/get")).encode(), -32601),
        (json.dumps(message("texte")).encode(), -32602),
        (json.dumps(message({**DONNEES, "iban": "FR76"})).encode(), -32602),
        (json.dumps(message({**DONNEES, "departement": "69003"})).encode(), -32602),
        (json.dumps(message({**DONNEES, "date_survenance": "14/08/2026"})).encode(), -32602),
    ],
    ids=[
        "illisible",
        "enveloppe",
        "méthode",
        "pas de data",
        "champ interdit",
        "code postal",
        "date",
    ],
)
def test_les_erreurs_du_contrat(corps: bytes, code: int) -> None:
    reponse = client.post("/a2a", content=corps, headers=ENTETES).json()
    assert reponse["error"]["code"] == code


def test_jeton_absent_et_doublon() -> None:
    assert client.post("/a2a", json=message(DONNEES)).status_code == 401
    client.post("/a2a", json=message(DONNEES), headers=ENTETES)
    second = client.post("/a2a", json=message(DONNEES), headers=ENTETES).json()
    assert second["error"]["code"] == -32029


@pytest.mark.parametrize(
    ("modifs", "niveau", "indicateurs"),
    [
        (
            {"montant_declare": 9000.0, "anciennete_contrat_jours": 30},
            "modere",
            ["MONTANT_ELEVE", "SINISTRE_PRECOCE"],
        ),
        (
            {"montant_declare": 9000.0, "anciennete_contrat_jours": 30, "sinistres_12_mois": 4},
            "eleve",
            ["MONTANT_ELEVE", "SINISTRE_PRECOCE", "FREQUENCE_ELEVEE"],
        ),
    ],
)
def test_le_score_est_explicable(
    modifs: dict[str, Any], niveau: str, indicateurs: list[str]
) -> None:
    evaluation = partenaire.evaluer({**DONNEES, **modifs})
    assert (evaluation["niveau"], evaluation["indicateurs"]) == (niveau, indicateurs)


def test_kaldera_dialogue_avec_notre_partenaire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bout en bout : notre client A2A valide les réponses de notre partenaire, en vrai HTTP."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    serveur = uvicorn.Server(
        uvicorn.Config(partenaire.app, host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=serveur.run, daemon=True).start()
    while not serveur.started:
        time.sleep(0.05)
    try:
        d = demande(
            sinistre={"montant_declare": 6000.0},
            pieces=[
                {"type": "facture", "lisible": True, "montant": 6000.0},
                {"type": "photo", "lisible": True},
            ],
        )
        fiche = kaldera.traiter_demande(d, partenaire_url=f"http://127.0.0.1:{port}")
        assert fiche["avis_fraude"] == {"niveau": "faible", "score": 0.28}
        assert fiche["decision"] == "acceptee" and fiche["mode_degrade"] is False
    finally:
        serveur.should_exit = True
