"""Outillage de la suite d'acceptance : partenaire simulé, scénarios, vérifications."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
import uvicorn

RACINE = Path(__file__).resolve().parents[2]
JETON_RECETTE = "jeton-recette"
os.environ["PARTENAIRE_JETON"] = JETON_RECETTE

# Engagement de service : une issue en 10 s au plus par demande (specs_metier.md, §12).
DUREE_MAX_DEMANDE_S = 10.0
MARGE_S = 1.5

SECTIONS_METIER = ("eligibilite", "pieces", "estimation", "avis_fraude", "issue")
CHAMPS_CONTRAT = {
    "reference_dossier",
    "type_sinistre",
    "montant_declare",
    "date_survenance",
    "anciennete_contrat_jours",
    "sinistres_12_mois",
    "departement",
}

SCENARIOS: list[dict[str, Any]] = [
    json.loads(ligne)
    for ligne in (RACINE / "eval" / "scenarios.jsonl").read_text(encoding="utf-8").splitlines()
    if ligne.strip()
]


def scenarios(*categories: str) -> list[Any]:
    return [
        pytest.param(s, id=s["id"])
        for s in SCENARIOS
        if not categories or s["categorie"] in categories
    ]


# ------------------------------------------------------------ partenaire simulé


class Partenaire:
    """Pilote le partenaire anti-fraude simulé lancé pour la session de test."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._client = httpx.Client(base_url=url, timeout=5.0)

    def preparer(self, reglage: dict[str, Any]) -> None:
        """Remet le journal à zéro et applique le comportement prévu par le scénario."""
        self._client.post("/_sim/reset").raise_for_status()
        self._client.post("/_sim/mode", json=reglage).raise_for_status()

    def journal(self) -> list[dict[str, Any]]:
        return self._client.get("/_sim/journal").json()


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def partenaire() -> Partenaire:
    from external_agent.app import app

    port = _port_libre()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    serveur = uvicorn.Server(config)
    threading.Thread(target=serveur.run, daemon=True).start()
    limite = time.monotonic() + 10
    while not serveur.started:
        if time.monotonic() > limite:
            pytest.fail("le partenaire simulé n'a pas démarré")
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}"
    os.environ["PARTENAIRE_URL"] = url
    yield Partenaire(url)
    serveur.should_exit = True


# ------------------------------------------------------------------- exécution


def executer_borne(
    libelle: str, delai_s: float, fonction: Callable[..., Any], *args: Any, **kwargs: Any
) -> tuple[Any, float]:
    """Exécute ``fonction`` en échouant proprement si elle ne rend pas la main à temps."""
    resultat: dict[str, Any] = {}

    def cible() -> None:
        try:
            resultat["valeur"] = fonction(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — relancée dans le thread de test
            resultat["erreur"] = exc

    debut = time.perf_counter()
    fil = threading.Thread(target=cible, daemon=True)
    fil.start()
    fil.join(delai_s)
    duree = time.perf_counter() - debut
    if fil.is_alive():
        pytest.fail(
            f"{libelle} : aucune issue après {delai_s:.1f} s — le traitement ne rend pas la main"
        )
    if "erreur" in resultat:
        raise resultat["erreur"]
    return resultat["valeur"], duree


def traiter(demande: dict[str, Any], partenaire: Partenaire) -> tuple[dict[str, Any], float]:
    import kaldera

    return executer_borne(
        demande["reference"],
        DUREE_MAX_DEMANDE_S + MARGE_S,
        kaldera.traiter_demande,
        demande,
        partenaire_url=partenaire.url,
    )


def traiter_lot(
    demandes: list[dict[str, Any]], partenaire: Partenaire
) -> tuple[dict[str, Any], float]:
    import kaldera

    return executer_borne(
        f"lot de {len(demandes)} demande(s)",
        DUREE_MAX_DEMANDE_S * len(demandes) + MARGE_S,
        kaldera.traiter_lot,
        demandes,
        partenaire_url=partenaire.url,
    )


# ---------------------------------------------------------------- vérifications


def verifier_issue_motivee(fiche: dict[str, Any], reference: str) -> None:
    assert isinstance(fiche, dict), f"{reference} : la fiche n'est pas un objet ({fiche!r})"
    assert fiche.get("reference") == reference, (
        f"{reference} : fiche reçue pour {fiche.get('reference')!r}"
    )
    issue = fiche.get("issue")
    assert issue in ("decision", "escalade"), (
        f"{reference} : issue {issue!r} — ni décision ni escalade (motif : {fiche.get('motif')!r})"
    )
    motif = fiche.get("motif")
    assert isinstance(motif, str) and len(motif.strip()) >= 3, (
        f"{reference} : issue sans motif ({motif!r})"
    )
    if issue == "decision":
        assert fiche.get("decision") in ("acceptee", "refusee"), (
            f"{reference} : décision {fiche.get('decision')!r} invalide"
        )
        montant = fiche.get("montant_rembourse")
        assert isinstance(montant, (int, float)) and montant >= 0, (
            f"{reference} : montant remboursé {montant!r} invalide"
        )
    else:
        assert isinstance(fiche.get("file"), str) and fiche["file"], (
            f"{reference} : escalade sans file destinataire"
        )


def verifier_issue_attendue(fiche: dict[str, Any], attendu: dict[str, Any]) -> None:
    reference = attendu["reference"]
    verifier_issue_motivee(fiche, reference)
    contexte = f"{reference} (motif : {fiche.get('motif')!r})"
    for champ in ("issue", "decision", "file"):
        if champ in attendu:
            assert fiche.get(champ) == attendu[champ], (
                f"{contexte} : {champ} = {fiche.get(champ)!r}, attendu {attendu[champ]!r}"
            )
    if "montant_rembourse" in attendu:
        obtenu, prevu = fiche.get("montant_rembourse"), attendu["montant_rembourse"]
        if prevu is None:
            assert obtenu is None, f"{contexte} : montant remboursé {obtenu!r}, attendu null"
        else:
            assert obtenu is not None and abs(obtenu - prevu) < 0.01, (
                f"{contexte} : montant remboursé {obtenu!r}, attendu {prevu!r}"
            )
    if "mode_degrade" in attendu:
        assert bool(fiche.get("mode_degrade")) is attendu["mode_degrade"], (
            f"{contexte} : mode_degrade = {fiche.get('mode_degrade')!r}, attendu {attendu['mode_degrade']!r}"
        )
    if "avis_fraude" in attendu:
        avis = fiche.get("avis_fraude")
        if attendu["avis_fraude"] is None:
            assert avis is None, f"{contexte} : avis anti-fraude {avis!r}, attendu null"
        else:
            assert isinstance(avis, dict) and avis.get("niveau") == attendu["avis_fraude"], (
                f"{contexte} : avis anti-fraude {avis!r}, niveau attendu {attendu['avis_fraude']!r}"
            )
    if attendu.get("arret"):
        arret = fiche.get("arret")
        assert isinstance(arret, dict) and arret.get("borne"), (
            f"{contexte} : arrêt non signalé (arret = {arret!r})"
        )


def auteurs_des_sections(fiche: dict[str, Any]) -> dict[str, set[str]]:
    trace = fiche.get("trace")
    reference = fiche.get("reference")
    assert isinstance(trace, list) and trace, f"{reference} : trace absente ou vide"
    auteurs: dict[str, set[str]] = defaultdict(set)
    for etape in trace:
        assert isinstance(etape, dict) and etape.get("agent"), (
            f"{reference} : étape sans agent ({etape!r})"
        )
        assert isinstance(etape.get("ecrit"), list), (
            f"{reference} : étape sans liste « ecrit » ({etape!r})"
        )
        for section in etape["ecrit"]:
            if section in SECTIONS_METIER:
                auteurs[section].add(etape["agent"])
    return auteurs


def verifier_roles(fiche: dict[str, Any], sections_requises: tuple[str, ...] = ()) -> None:
    reference = fiche.get("reference")
    auteurs = auteurs_des_sections(fiche)
    for section in ("eligibilite", "issue", *sections_requises):
        assert section in auteurs, f"{reference} : aucune étape n'a écrit la section « {section} »"
    for section, agents in auteurs.items():
        assert len(agents) == 1, (
            f"{reference} : la section « {section} » a été écrite par plusieurs agents ({', '.join(sorted(agents))})"
        )
    sections_par_agent: dict[str, set[str]] = defaultdict(set)
    for section, agents in auteurs.items():
        for agent in agents:
            sections_par_agent[agent].add(section)
    for agent, sections in sections_par_agent.items():
        assert len(sections) == 1, (
            f"{reference} : l'agent « {agent} » a écrit plusieurs sections métier ({', '.join(sorted(sections))})"
        )


def valeurs_personnelles(demande: dict[str, Any]) -> list[str]:
    assure = demande["assure"]
    valeurs = [
        assure[c]
        for c in (
            "id_client",
            "nom",
            "prenom",
            "email",
            "telephone",
            "iban",
            "adresse",
            "code_postal",
        )
    ]
    valeurs += [demande["contrat"]["numero"], demande["sinistre"]["description"]]
    return [v for v in valeurs if isinstance(v, str) and v]
