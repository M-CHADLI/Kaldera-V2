"""Acceptance — l'équipe d'agents et son orchestration."""

from __future__ import annotations

from typing import Any

import pytest

import kaldera
from conftest import (
    DUREE_MAX_DEMANDE_S,
    MARGE_S,
    SCENARIOS,
    Partenaire,
    scenarios,
    traiter,
    traiter_lot,
    verifier_issue_attendue,
    verifier_issue_motivee,
    verifier_roles,
)


@pytest.mark.parametrize("scenario", scenarios("nominal"))
def test_scenario_nominal_produit_la_decision_attendue(
    scenario: dict[str, Any], partenaire: Partenaire
) -> None:
    """Étant donné un scénario métier nominal, quand il est soumis, alors l'équipe
    produit la décision attendue, chaque agent ayant tenu son rôle."""
    partenaire.preparer(scenario["partenaire"])
    for demande, attendu in zip(scenario["demandes"], scenario["attendu"], strict=True):
        fiche, _ = traiter(demande, partenaire)
        verifier_issue_attendue(fiche, attendu)
        requises = ("pieces", "estimation") if fiche.get("decision") == "acceptee" else ()
        verifier_roles(fiche, requises)


@pytest.mark.parametrize("scenario", scenarios())
def test_toute_demande_aboutit_a_une_decision_ou_une_escalade_motivee(
    scenario: dict[str, Any], partenaire: Partenaire
) -> None:
    """Étant donné n'importe quel scénario du jeu de test, quand il se termine, alors
    l'issue est une décision ou une escalade motivée — jamais un blocage silencieux."""
    partenaire.preparer(scenario["partenaire"])
    resultat, _ = traiter_lot(scenario["demandes"], partenaire)
    fiches = resultat.get("fiches") if isinstance(resultat, dict) else None
    assert isinstance(fiches, list) and len(fiches) == len(scenario["demandes"]), (
        f"{scenario['id']} : {len(scenario['demandes'])} fiche(s) attendue(s), reçu {fiches!r}"
    )
    for demande, fiche in zip(scenario["demandes"], fiches, strict=True):
        verifier_issue_motivee(fiche, demande["reference"])


def test_scenario_piege_a_boucle_s_arrete_dans_les_bornes(partenaire: Partenaire) -> None:
    """Étant donné le scénario piège à boucle, quand il est rejoué, alors l'exécution
    s'arrête dans les bornes définies, arrêt signalé."""
    (scenario,) = [s for s in SCENARIOS if s["categorie"] == "boucle"]
    partenaire.preparer(scenario["partenaire"])
    (demande,), (attendu,) = scenario["demandes"], scenario["attendu"]

    fiche, duree = traiter(demande, partenaire)
    verifier_issue_attendue(fiche, attendu)

    assert callable(getattr(kaldera, "bornes", None)), (
        "kaldera.bornes() n'est pas exposée (docs/interface.md)"
    )
    bornes = kaldera.bornes()
    etapes_max, duree_max_s = bornes.get("etapes_max"), bornes.get("duree_max_s")
    assert isinstance(etapes_max, int) and etapes_max > 0, (
        f"borne etapes_max invalide : {etapes_max!r}"
    )
    assert isinstance(duree_max_s, (int, float)) and 0 < duree_max_s <= DUREE_MAX_DEMANDE_S, (
        f"borne duree_max_s invalide : {duree_max_s!r} (au plus {DUREE_MAX_DEMANDE_S} s)"
    )
    assert len(fiche["trace"]) <= etapes_max, (
        f"{len(fiche['trace'])} étapes consommées pour une borne de {etapes_max}"
    )
    assert duree <= duree_max_s + MARGE_S, (
        f"traitement en {duree:.1f} s pour une borne de {duree_max_s} s"
    )
