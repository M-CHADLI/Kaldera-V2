"""Acceptance — la collaboration A2A avec le partenaire anti-fraude et l'épreuve du réel."""

from __future__ import annotations

import json
from typing import Any

import pytest

from conftest import (
    CHAMPS_CONTRAT,
    Partenaire,
    scenarios,
    traiter,
    traiter_lot,
    valeurs_personnelles,
    verifier_issue_attendue,
    verifier_roles,
)


def _appels(partenaire: Partenaire, reference: str) -> list[dict[str, Any]]:
    """Appels reçus par le partenaire pour un dossier (ou dont il n'a pu lire la référence)."""
    return [e for e in partenaire.journal() if e.get("reference") in (reference, None)]


def _corps_lisible(entree: dict[str, Any]) -> str:
    brut = entree.get("corps_brut") or ""
    try:
        return json.dumps(json.loads(brut), ensure_ascii=False)
    except ValueError:
        return brut


def _decrire(entree: dict[str, Any]) -> str:
    return f"HTTP {entree.get('statut_http')}, erreurs {entree.get('erreurs') or '—'}"


@pytest.mark.parametrize("scenario", scenarios("antifraude"))
def test_echange_antifraude_respecte_le_contrat_et_ne_transmet_que_les_donnees_autorisees(
    scenario: dict[str, Any], partenaire: Partenaire
) -> None:
    """Étant donné une demande nécessitant l'anti-fraude, quand elle est traitée, alors
    l'échange respecte le contrat et seules les données autorisées sont transmises."""
    partenaire.preparer(scenario["partenaire"])
    for demande, attendu in zip(scenario["demandes"], scenario["attendu"], strict=True):
        reference = demande["reference"]
        fiche, _ = traiter(demande, partenaire)

        appels = _appels(partenaire, reference)
        assert appels, f"{reference} : le partenaire anti-fraude n'a pas été consulté"
        assert len(appels) == 1, (
            f"{reference} : {len(appels)} appels reçus par le partenaire — un seul autorisé par dossier "
            f"({'; '.join(_decrire(a) for a in appels)})"
        )
        (appel,) = appels
        hors_contrat = sorted(set(appel["champs"]) - CHAMPS_CONTRAT)
        assert not hors_contrat, (
            f"{reference} : données hors contrat transmises : {', '.join(hors_contrat)}"
        )
        corps = _corps_lisible(appel)
        fuites = [v for v in valeurs_personnelles(demande) if v in corps]
        assert not fuites, f"{reference} : données personnelles transmises au partenaire : {fuites}"
        assert appel["conforme"] and appel["statut_http"] == 200, (
            f"{reference} : requête refusée par le partenaire ({_decrire(appel)})"
        )

        verifier_issue_attendue(fiche, attendu)
        avis_partenaire = appel["reponse"]["result"]["artifacts"][0]["parts"][0]["data"]
        assert fiche["avis_fraude"].get("score") == avis_partenaire["score"], (
            f"{reference} : score retenu {fiche['avis_fraude'].get('score')!r}, "
            f"le partenaire a répondu {avis_partenaire['score']!r}"
        )
        verifier_roles(fiche, ("avis_fraude",))


@pytest.mark.parametrize("scenario", scenarios("invalide"))
def test_reponse_invalide_du_partenaire_est_rejetee_et_non_propagee(
    scenario: dict[str, Any], partenaire: Partenaire
) -> None:
    """Étant donné une réponse invalide du partenaire, quand elle est reçue, alors elle
    est rejetée et non propagée."""
    partenaire.preparer(scenario["partenaire"])
    for demande, attendu in zip(scenario["demandes"], scenario["attendu"], strict=True):
        reference = demande["reference"]
        fiche, _ = traiter(demande, partenaire)

        appels = _appels(partenaire, reference)
        assert appels and appels[0]["conforme"], (
            f"{reference} : la requête n'a pas été acceptée par le partenaire "
            f"({_decrire(appels[0]) if appels else 'aucun appel'}) — sa réponse n'a pas pu être éprouvée"
        )
        assert len(appels) == 1, (
            f"{reference} : {len(appels)} appels — aucune relance n'est autorisée"
        )

        assert fiche.get("avis_fraude") is None, (
            f"{reference} : réponse non conforme reprise dans la fiche ({fiche.get('avis_fraude')!r})"
        )
        sans_trace = json.dumps(
            {k: v for k, v in fiche.items() if k != "trace"}, ensure_ascii=False
        )
        assert "EVA-NC" not in sans_trace and "rembourser_integralement" not in sans_trace, (
            f"{reference} : contenu de la réponse non conforme propagé dans la fiche"
        )
        verifier_issue_attendue(fiche, attendu)


@pytest.mark.parametrize("scenario", scenarios("panne"))
def test_partenaire_en_panne_le_mode_degrade_s_applique_sans_bloquer_le_reste(
    scenario: dict[str, Any], partenaire: Partenaire
) -> None:
    """Étant donné le partenaire en panne, quand les demandes du scénario arrivent, alors
    le mode dégradé prévu s'applique, le reste n'est pas bloqué, et les métriques par
    agent sont visibles."""
    partenaire.preparer(scenario["partenaire"])
    resultat, _ = traiter_lot(scenario["demandes"], partenaire)

    fiches = {f.get("reference"): f for f in resultat.get("fiches", []) if isinstance(f, dict)}
    for attendu in scenario["attendu"]:
        assert attendu["reference"] in fiches, f"{attendu['reference']} : aucune fiche produite"
        verifier_issue_attendue(fiches[attendu["reference"]], attendu)

    for demande in scenario["demandes"]:
        appels = [e for e in partenaire.journal() if e.get("reference") == demande["reference"]]
        assert len(appels) <= 1, (
            f"{demande['reference']} : {len(appels)} appels — aucune relance n'est autorisée"
        )

    metriques = resultat.get("metriques")
    agents = {etape.get("agent") for f in fiches.values() for etape in f.get("trace", [])}
    assert isinstance(metriques, dict) and agents, "métriques par agent absentes"
    manquants = sorted(a for a in agents if not isinstance(metriques.get(a), dict))
    assert not manquants, f"métriques absentes pour : {', '.join(map(str, manquants))}"
    for agent in agents:
        for cle in ("appels", "echecs", "latence_ms", "appels_externes"):
            valeur = metriques[agent].get(cle)
            assert isinstance(valeur, (int, float)) and not isinstance(valeur, bool), (
                f"métrique {cle!r} invalide pour {agent} : {valeur!r}"
            )
    assert sum(m["appels_externes"] for a, m in metriques.items() if a in agents) >= 1, (
        "aucun recours au partenaire visible dans les métriques"
    )
    assert sum(m["echecs"] for a, m in metriques.items() if a in agents) >= 1, (
        "l'indisponibilité du partenaire n'apparaît dans aucune métrique d'échec"
    )
