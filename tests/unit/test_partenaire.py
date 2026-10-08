"""Client A2A : liste blanche, délai, validation en trois couches, doublons, disjoncteur."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx
import pytest

from kaldera import partenaire as p
from kaldera.vues import champs_contrat

from fabrique import AVIS_FAIBLE, demande

REF = AVIS_FAIBLE["reference_dossier"]


def enveloppe(evaluation: dict[str, Any] | None = None, id_rpc: str = "id-1") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id_rpc,
        "result": {
            "kind": "task",
            "status": {"state": "completed"},
            "artifacts": [{"parts": [{"kind": "data", "data": evaluation or dict(AVIS_FAIBLE)}]}],
        },
    }


def valider(corps: Any, statut: int = 200) -> dict[str, Any]:
    brut = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
    return p.valider_reponse(statut, brut, "id-1", REF)


def avec(**champs: Any) -> dict[str, Any]:
    return enveloppe({**AVIS_FAIBLE, **champs})


def test_une_reponse_conforme_est_reduite_aux_champs_du_contrat() -> None:
    avis = valider(enveloppe())
    assert set(avis) == p.CHAMPS_EVALUATION and avis["niveau"] == "faible"


def _sans(cle: str) -> dict[str, Any]:
    corps = enveloppe()
    del corps[cle]
    return corps


def _resultat(modif: Any) -> dict[str, Any]:
    corps = enveloppe()
    corps["result"] = modif(deepcopy(corps["result"]))
    return corps


CAS_REJETES = [
    ("statut HTTP", enveloppe(), 400, "transport"),
    ("pas du JSON", b"<html>maintenance</html>", 200, "transport"),
    ("pas un objet", [1, 2], 200, "transport"),
    ("version JSON-RPC", {**enveloppe(), "jsonrpc": "1.0"}, 200, "transport"),
    ("autre identifiant", enveloppe(id_rpc="autre"), 200, "transport"),
    ("ni result ni error", _sans("result"), 200, "transport"),
    ("result et error", {**enveloppe(), "error": {"code": 1}}, 200, "transport"),
    (
        "erreur JSON-RPC",
        {"jsonrpc": "2.0", "id": "id-1", "error": {"code": -32029}},
        200,
        "transport",
    ),
    (
        "tâche non terminée",
        _resultat(lambda r: {**r, "status": {"state": "working"}}),
        200,
        "schema",
    ),
    ("deux artefacts", _resultat(lambda r: {**r, "artifacts": r["artifacts"] * 2}), 200, "schema"),
    ("structure cassée", _resultat(lambda r: {"kind": "task"}), 200, "schema"),
    ("champ hors contrat", avec(decision_recommandee="rembourser_integralement"), 200, "schema"),
    (
        "champ absent",
        enveloppe({k: v for k, v in AVIS_FAIBLE.items() if k != "niveau"}),
        200,
        "schema",
    ),
    ("score textuel", avec(score="0.1"), 200, "schema"),
    ("niveau inconnu", avec(niveau="nul"), 200, "schema"),
    ("indicateur inconnu", avec(indicateurs=["AUTRE"]), 200, "schema"),
    ("identifiant numérique", avec(evaluation_id=7), 200, "schema"),
    ("score hors bornes", avec(score=1.7, niveau="eleve"), 200, "plausibilite"),
    ("niveau incohérent", avec(score=0.91, niveau="faible"), 200, "plausibilite"),
    ("autre dossier", avec(reference_dossier="KAL-26-9999"), 200, "plausibilite"),
]


@pytest.mark.parametrize(
    ("cas", "corps", "statut", "couche"), CAS_REJETES, ids=[c[0] for c in CAS_REJETES]
)
def test_une_reponse_non_conforme_est_rejetee_par_la_bonne_couche(
    cas: str, corps: Any, statut: int, couche: str
) -> None:
    with pytest.raises(p.ReponseRejetee) as rejet:
        valider(corps, statut)
    assert rejet.value.couche == couche
    assert "rembourser" not in rejet.value.raison  # aucun contenu du partenaire recopié


@pytest.mark.parametrize(("score", "niveau"), [(0.0, "faible"), (0.4, "modere"), (0.75, "eleve")])
def test_les_seuils_de_niveau_suivent_le_contrat(score: float, niveau: str) -> None:
    assert p.niveau_attendu(score) == niveau


def test_la_requete_ne_contient_que_les_sept_champs_du_contrat() -> None:
    donnees = {**champs_contrat(demande()), "iban": "FR76"}
    requete = p.construire_requete(donnees)
    (partie,) = requete["params"]["message"]["parts"]
    assert set(partie["data"]) == set(p.CHAMPS_REQUETE)


def _faux_post(reponse: Any) -> Any:
    def post(url: str, json: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
        post.requete = json  # type: ignore[attr-defined]
        post.timeout = timeout  # type: ignore[attr-defined]
        if isinstance(reponse, Exception):
            raise reponse
        if reponse == "conforme":
            return httpx.Response(200, content=json_dumps(enveloppe(id_rpc=json["id"])))
        return reponse

    return post


def json_dumps(corps: dict[str, Any]) -> bytes:
    return json.dumps(corps).encode()


@pytest.mark.parametrize(
    ("reponse", "couche"),
    [
        (httpx.ReadTimeout("lent"), "delai"),
        (httpx.ConnectError("refus"), "panne"),
        (httpx.Response(503, content=b"{}"), "panne"),
        (httpx.Response(200, content=b"<html>"), "transport"),
    ],
)
def test_consulter_classe_chaque_echec(
    monkeypatch: pytest.MonkeyPatch, reponse: Any, couche: str
) -> None:
    monkeypatch.setattr(p.httpx, "post", _faux_post(reponse))
    consultation = p.consulter(champs_contrat(demande()), "http://partenaire", 3.0)
    assert consultation.avis is None and consultation.couche == couche


def test_consulter_rend_l_avis_valide(monkeypatch: pytest.MonkeyPatch) -> None:
    faux = _faux_post("conforme")
    monkeypatch.setattr(p.httpx, "post", faux)
    consultation = p.consulter(champs_contrat(demande()), "http://partenaire", 3.0)
    assert consultation.avis is not None and consultation.avis["score"] == 0.12
    assert faux.timeout == 3.0  # type: ignore[attr-defined]


def test_le_client_refuse_un_second_appel_pour_le_meme_dossier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        p, "consulter", lambda donnees, url, delai: p.Consultation(dict(AVIS_FAIBLE))
    )
    client = p.ClientPartenaire("http://partenaire")
    donnees = champs_contrat(demande())
    assert client.consulter(donnees).avis is not None
    second = client.consulter(donnees)
    assert second.couche == "doublon" and not second.appel_effectue


def test_le_disjoncteur_s_ouvre_apres_n_pannes(monkeypatch: pytest.MonkeyPatch) -> None:
    delais: list[float] = []

    def en_panne(donnees: dict[str, Any], url: str, delai: float) -> p.Consultation:
        delais.append(delai)
        return p.Consultation(None, "panne", "HTTP 503")

    monkeypatch.setattr(p, "consulter", en_panne)
    client = p.ClientPartenaire("http://partenaire", delai_s=3.0, seuil_pannes=2)
    for numero in (1, 2):
        client.consulter(champs_contrat(demande(reference=f"KAL-26-000{numero}")), delai_s=10.0)
    ouvert = client.consulter(champs_contrat(demande(reference="KAL-26-0003")))
    assert ouvert.couche == "disjoncteur" and not ouvert.appel_effectue
    assert delais == [3.0, 3.0]  # le délai du contrat n'est jamais dépassé


def test_url_partenaire_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PARTENAIRE_URL", raising=False)
    assert p.url_partenaire() == p.URL_PAR_DEFAUT
    assert p.url_partenaire("http://x/") == "http://x"
