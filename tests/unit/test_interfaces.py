"""Console web et ligne de commande."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from kaldera import cli, web

from fabrique import demande

client = TestClient(web.app)
URL_TEST = "http://partenaire.test"
SIMULE = {"/_sim/etat": 200, "/health": 404, "/.well-known/agent.json": 200}
REEL = {"/_sim/etat": 404, "/health": 200, "/.well-known/agent.json": 200}


def brancher(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, int], sondes: list[str] | None = None
) -> None:
    """Simule ``httpx.get`` : chaque route connue répond son code, les autres sont muettes."""

    def get(url: str, **_: Any) -> httpx.Response:
        if sondes is not None:
            sondes.append(urlsplit(url).path)
        statut = routes.get(urlsplit(url).path)
        if statut is None:
            raise httpx.ConnectError("refus")
        return httpx.Response(statut)

    monkeypatch.setenv("PARTENAIRE_URL", URL_TEST)
    monkeypatch.setattr(httpx, "get", get)


@pytest.fixture
def partenaire_simule(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    reglages: list[dict[str, Any]] = []
    brancher(monkeypatch, SIMULE)
    monkeypatch.setattr(web, "regler_partenaire", reglages.append)
    return reglages


def test_la_console_et_les_routes_de_lecture() -> None:
    assert "KALDERA" in client.get("/").text
    scenarios = client.get("/api/scenarios").json()
    assert len(scenarios) == 28 and {"id", "categorie", "titre"} <= set(scenarios[0])
    assert client.get("/api/bornes").json()["duree_max_s"] <= 10


def test_rejouer_un_scenario_compare_a_l_attendu(partenaire_simule: list[dict[str, Any]]) -> None:
    reponse = client.post("/api/scenarios/NOM-02/rejouer").json()
    assert reponse["conformes"] == [True] and partenaire_simule == [{"mode": "normal"}]
    assert reponse["type_partenaire"] == "simulé" and reponse["reglage"] == {"mode": "normal"}
    client.post("/api/scenarios/NOM-02/rejouer?mode=panne")
    assert partenaire_simule[-1] == {"mode": "panne"}


def test_rejouer_signale_les_erreurs(
    monkeypatch: pytest.MonkeyPatch, partenaire_simule: list[dict[str, Any]]
) -> None:
    assert client.post("/api/scenarios/INCONNU/rejouer").status_code == 404
    assert client.post("/api/scenarios/NOM-02/rejouer?mode=farfelu").status_code == 422

    def injoignable(reglage: dict[str, Any]) -> None:
        raise httpx.ConnectError("refus")

    monkeypatch.setattr(web, "regler_partenaire", injoignable)
    assert client.post("/api/scenarios/NOM-02/rejouer").status_code == 502
    brancher(monkeypatch, {})
    reponse = client.post("/api/scenarios/NOM-02/rejouer")
    assert reponse.status_code == 502 and URL_TEST in reponse.json()["detail"]


def test_rejouer_avec_un_partenaire_reel_ne_regle_rien(monkeypatch: pytest.MonkeyPatch) -> None:
    sondes: list[str] = []
    brancher(monkeypatch, REEL, sondes)
    reglages: list[dict[str, Any]] = []
    monkeypatch.setattr(web, "regler_partenaire", reglages.append)

    reponse = client.post("/api/scenarios/NOM-02/rejouer")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["type_partenaire"] == "réel" and corps["reglage"] is None
    assert corps["conformes"] == [True]
    # Aucun réglage /_sim : seule la sonde de détection, en lecture, touche le banc.
    assert reglages == [] and [s for s in sondes if s.startswith("/_sim")] == ["/_sim/etat"]


@pytest.mark.parametrize("mode", ["normal", "lent", "invalide", "panne"])
def test_un_mode_force_est_refuse_avec_un_partenaire_reel(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    brancher(monkeypatch, REEL)
    reglages: list[dict[str, Any]] = []
    monkeypatch.setattr(web, "regler_partenaire", reglages.append)

    reponse = client.post(f"/api/scenarios/NOM-02/rejouer?mode={mode}")
    assert reponse.status_code == 409 and reglages == []
    assert "réel" in reponse.json()["detail"] and mode in reponse.json()["detail"]


def test_soumettre_une_demande() -> None:
    fiche = client.post("/api/demandes", json=demande(contrat={"statut": "resilie"})).json()
    assert fiche["decision"] == "refusee"
    assert client.post("/api/demandes", json={"reference": "KAL-26-0000"}).status_code == 422


def test_sante_signale_un_partenaire_injoignable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")
    assert client.get("/api/sante").json()["partenaire"] == "injoignable"


@pytest.mark.parametrize(
    ("routes", "partenaire", "type_"),
    [
        (SIMULE, "en ligne", "simulé"),
        ({**SIMULE, "/.well-known/agent.json": 503}, "en ligne", "simulé"),
        (REEL, "en ligne", "réel"),
        ({**REEL, "/health": 404}, "en ligne", "réel"),
        ({"/_sim/etat": 404, "/health": 503, "/.well-known/agent.json": 503}, "injoignable", None),
        ({}, "injoignable", None),
    ],
    ids=["simule", "simule-en-panne", "reel", "reel-sans-health", "reel-en-panne", "muet"],
)
def test_sante_detecte_le_type_de_partenaire(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, int], partenaire: str, type_: str | None
) -> None:
    brancher(monkeypatch, routes)
    assert client.get("/api/sante").json() == {
        "kaldera": "ok",
        "partenaire": partenaire,
        "type": type_,
        "url_partenaire": URL_TEST,
    }


def test_un_partenaire_muet_n_est_sonde_qu_une_fois(monkeypatch: pytest.MonkeyPatch) -> None:
    sondes: list[str] = []
    brancher(monkeypatch, {}, sondes)
    assert web.type_partenaire() is None and sondes == ["/_sim/etat"]


@pytest.mark.parametrize(
    ("fiche", "attendu", "ok"),
    [
        ({"issue": "decision", "montant_rembourse": 10.0}, {"montant_rembourse": 10.0}, True),
        ({"issue": "decision", "montant_rembourse": 9.0}, {"montant_rembourse": 10.0}, False),
        ({"issue": "escalade"}, {"issue": "decision"}, False),
        ({"avis_fraude": None}, {"avis_fraude": "faible"}, False),
        ({"arret": None}, {"arret": True}, False),
    ],
)
def test_conformite_a_l_attendu(fiche: dict[str, Any], attendu: dict[str, Any], ok: bool) -> None:
    assert web.conforme(fiche, attendu) is ok


def test_la_ligne_de_commande_rejoue_un_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario = {
        "id": "T-01",
        "titre": "non éligible",
        "demandes": [demande(contrat={"statut": "resilie"})],
    }
    autre = {**scenario, "id": "T-02"}
    fichier = tmp_path / "scenarios.jsonl"
    fichier.write_text(f"{json.dumps(scenario)}\n\n{json.dumps(autre)}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["kaldera", str(fichier), "--scenario", "T-01", "--trace"])
    cli.main()
    sortie = capsys.readouterr().out
    assert "T-01" in sortie and "T-02" not in sortie and '"trace"' in sortie
