"""Console web et ligne de commande."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from kaldera import cli, web

from fabrique import demande

client = TestClient(web.app)


@pytest.fixture
def partenaire_simule(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    reglages: list[dict[str, Any]] = []
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
    client.post("/api/scenarios/NOM-02/rejouer?mode=panne")
    assert partenaire_simule[-1] == {"mode": "panne"}


def test_rejouer_signale_les_erreurs(monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.post("/api/scenarios/INCONNU/rejouer").status_code == 404
    assert client.post("/api/scenarios/NOM-02/rejouer?mode=farfelu").status_code == 422

    def injoignable(reglage: dict[str, Any]) -> None:
        raise httpx.ConnectError("refus")

    monkeypatch.setattr(web, "regler_partenaire", injoignable)
    assert client.post("/api/scenarios/NOM-02/rejouer").status_code == 502


def test_soumettre_une_demande() -> None:
    fiche = client.post("/api/demandes", json=demande(contrat={"statut": "resilie"})).json()
    assert fiche["decision"] == "refusee"
    assert client.post("/api/demandes", json={"reference": "KAL-26-0000"}).status_code == 422


def test_sante_signale_un_partenaire_injoignable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")
    assert client.get("/api/sante").json()["partenaire"] == "injoignable"


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
