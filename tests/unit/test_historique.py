"""Historique neutralisé : liste blanche, pseudonyme HMAC, jamais de donnée personnelle."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import kaldera
from kaldera import historique

from fabrique import demande

CHAMPS_LIGNE = {"horodatage", "reference", "client", "trace", *historique.CHAMPS_FICHE}


@pytest.fixture
def fichier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Historique activé dans un fichier temporaire, avec une clé de pseudonymisation."""
    chemin = tmp_path / "historique.jsonl"
    monkeypatch.setenv(historique.VARIABLE_CHEMIN, str(chemin))
    monkeypatch.setenv(historique.VARIABLE_CLE, "cle-de-test")
    return chemin


def lignes(chemin: Path) -> list[dict[str, Any]]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def valeurs_personnelles(d: dict[str, Any]) -> list[str]:
    """Chaque valeur de l'assuré, le numéro de contrat et la description libre."""
    return [
        *(str(valeur) for valeur in d["assure"].values()),
        d["contrat"]["numero"],
        d["sinistre"]["description"],
    ]


# ---------------------------------------------------------------- activation


def test_l_historique_est_desactive_par_defaut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(historique.VARIABLE_CHEMIN, raising=False)
    monkeypatch.chdir(tmp_path)
    kaldera.traiter_demande(demande())
    kaldera.traiter_lot([demande(reference="KAL-26-9002")])
    assert list(tmp_path.iterdir()) == []


def test_une_ligne_par_demande_traitee(fichier: Path) -> None:
    fiche = kaldera.traiter_demande(demande())
    (ligne,) = lignes(fichier)
    assert set(ligne) == CHAMPS_LIGNE
    assert ligne["reference"] == "KAL-26-9001"
    assert (ligne["decision"], ligne["montant_rembourse"]) == ("acceptee", 1650.0)
    assert ligne["rapport"] == fiche["rapport"]
    horodatage = datetime.fromisoformat(ligne["horodatage"])
    assert horodatage.utcoffset() == timedelta(0)


def test_un_lot_donne_une_ligne_par_demande(fichier: Path) -> None:
    references = [f"KAL-26-91{i:02d}" for i in range(6)]
    kaldera.traiter_lot([demande(reference=reference) for reference in references])
    assert sorted(ligne["reference"] for ligne in lignes(fichier)) == references


def test_les_lignes_s_ajoutent_sans_ecraser(fichier: Path) -> None:
    kaldera.traiter_demande(demande())
    kaldera.traiter_demande(demande(reference="KAL-26-9002"))
    assert [ligne["reference"] for ligne in lignes(fichier)] == ["KAL-26-9001", "KAL-26-9002"]


# -------------------------------------------------------------- neutralisation


def test_aucune_donnee_personnelle_n_est_stockee(fichier: Path) -> None:
    d = demande()
    kaldera.traiter_demande(d)
    kaldera.traiter_lot([demande(reference="KAL-26-9002")])
    texte = fichier.read_text(encoding="utf-8")
    for valeur in valeurs_personnelles(d):
        assert valeur not in texte, valeur
    for ligne in lignes(fichier):
        assert set(ligne) == CHAMPS_LIGNE
        assert "rapport_assure" not in ligne and "pieces" not in ligne


def test_la_trace_est_reduite_a_la_liste_blanche(fichier: Path) -> None:
    # Deux compléments demandés : la trace porte des détails (types, nouveaux_depots).
    fiche = kaldera.traiter_demande(demande(pieces=[]))
    assert any(set(etape) - set(historique.CHAMPS_TRACE) for etape in fiche["trace"])
    (ligne,) = lignes(fichier)
    assert len(ligne["trace"]) == len(fiche["trace"])
    for etape in ligne["trace"]:
        assert set(etape) <= set(historique.CHAMPS_TRACE)
        assert {"agent", "action", "ecrit", "statut", "duree_ms"} <= set(etape)
    assert ligne["trace"][-1]["regle"] == fiche["regle"]


# ----------------------------------------------------------------- pseudonyme


def test_le_pseudonyme_est_stable_avec_la_meme_cle(
    fichier: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kaldera.traiter_demande(demande())
    kaldera.traiter_demande(demande(reference="KAL-26-9002"))
    monkeypatch.setenv(historique.VARIABLE_CLE, "une-autre-cle")
    kaldera.traiter_demande(demande(reference="KAL-26-9003"))
    premier, second, autre = (ligne["client"] for ligne in lignes(fichier))
    assert premier == second != autre
    assert len(premier) == historique.LONGUEUR_PSEUDONYME
    int(premier, 16)  # hexadécimal
    assert premier != hashlib.sha256(b"C-001").hexdigest()[: historique.LONGUEUR_PSEUDONYME]


def test_deux_clients_ont_deux_pseudonymes(fichier: Path) -> None:
    kaldera.traiter_demande(demande())
    kaldera.traiter_demande(demande(reference="KAL-26-9002", assure={"id_client": "C-002"}))
    premier, second = (ligne["client"] for ligne in lignes(fichier))
    assert premier and second and premier != second


@pytest.mark.parametrize("cle", [None, ""])
def test_sans_cle_le_client_est_nul(
    fichier: Path, monkeypatch: pytest.MonkeyPatch, cle: str | None
) -> None:
    if cle is None:
        monkeypatch.delenv(historique.VARIABLE_CLE, raising=False)
    else:
        monkeypatch.setenv(historique.VARIABLE_CLE, cle)
    kaldera.traiter_demande(demande())
    (ligne,) = lignes(fichier)
    assert ligne["client"] is None
    assert "C-001" not in fichier.read_text(encoding="utf-8")


def test_une_demande_sans_assure_exploitable_reste_historisee(fichier: Path) -> None:
    ligne = historique.neutraliser(
        {"reference": "KAL-26-9009", "assure": "texte"}, {"reference": "KAL-26-9009"}
    )
    assert ligne["client"] is None and ligne["trace"] == []


# ------------------------------------------------------------------ robustesse


def test_un_chemin_inaccessible_ne_casse_pas_le_traitement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    obstacle = tmp_path / "un-fichier"
    obstacle.write_text("", encoding="utf-8")
    monkeypatch.setenv(historique.VARIABLE_CHEMIN, str(obstacle / "historique.jsonl"))
    with caplog.at_level(logging.WARNING, logger="kaldera.historique"):
        fiche = kaldera.traiter_demande(demande())
        resultat = kaldera.traiter_lot([demande(reference="KAL-26-9002")])
    assert fiche["decision"] == "acceptee"
    assert resultat["fiches"][0]["decision"] == "acceptee"
    avertissements = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avertissements) == 2
    assert "KAL-26-9001" in avertissements[0].getMessage()
