"""Équipe d'agents : frontières, bornes, filet de sécurité, décisions et rapports."""

from __future__ import annotations

from typing import Any

import pytest

import kaldera
from kaldera import decision, metriques
from kaldera.agents import Resultat
from kaldera.agents.estimation import calculer_montant
from kaldera.bornes import BORNES
from kaldera.etat import Etat, ViolationFrontiere
from kaldera.partenaire import Consultation
from kaldera.superviseur import Superviseur
from kaldera.vues import departement

from fabrique import AVIS_FAIBLE, FauxClient, demande


def traiter(
    d: dict[str, Any], consultation: Consultation | None = None, **bornes: Any
) -> dict[str, Any]:
    client = FauxClient(consultation or Consultation(dict(AVIS_FAIBLE)))
    return Superviseur(bornes={**BORNES, **bornes}, client=client).traiter(d)  # type: ignore[arg-type]


def auteurs(fiche: dict[str, Any]) -> dict[str, str]:
    return {s: e["agent"] for e in fiche["trace"] for s in e["ecrit"]}


# ------------------------------------------------------------------ parcours


def test_une_demande_simple_est_acceptee_et_chaque_section_a_son_auteur() -> None:
    fiche = traiter(demande())
    assert (fiche["decision"], fiche["montant_rembourse"]) == ("acceptee", 1650.0)
    assert auteurs(fiche) == {
        "eligibilite": "eligibilite",
        "pieces": "pieces",
        "estimation": "estimation",
        "avis_fraude": "antifraude",
        "issue": "superviseur",
    }


def test_une_demande_non_eligible_s_arrete_sans_appeler_le_partenaire() -> None:
    client = FauxClient(Consultation(dict(AVIS_FAIBLE)))
    d = demande(contrat={"statut": "resilie"}, sinistre={"montant_declare": 9000.0})
    fiche = Superviseur(client=client).traiter(d)  # type: ignore[arg-type]
    assert fiche["decision"] == "refusee" and not client.appels
    assert "non éligible" in fiche["rapport"] and "Pièces — non examinées" in fiche["rapport"]


def test_un_dommage_sous_la_franchise_est_refuse() -> None:
    d = demande(
        sinistre={"montant_declare": 100.0},
        pieces=[
            {"type": "facture", "lisible": True, "montant": 100.0},
            {"type": "photo", "lisible": True},
        ],
    )
    assert traiter(d)["regle"] == 3


@pytest.mark.parametrize(
    ("score", "niveau", "file"), [(0.5, "modere", "gestionnaire"), (0.9, "eleve", "cellule_fraude")]
)
def test_l_avis_du_partenaire_oriente_vers_la_bonne_file(
    score: float, niveau: str, file: str
) -> None:
    avis = {**AVIS_FAIBLE, "score": score, "niveau": niveau}
    d = demande(
        sinistre={"montant_declare": 6000.0},
        pieces=[
            {"type": "facture", "lisible": True, "montant": 6000.0},
            {"type": "photo", "lisible": True},
        ],
    )
    fiche = traiter(d, Consultation(avis))
    assert fiche["file"] == file and fiche["avis_fraude"] == {"niveau": niveau, "score": score}
    assert f"risque {'modéré' if niveau == 'modere' else 'élevé'}" in fiche["rapport"]


@pytest.mark.parametrize(("montant", "issue"), [(1400.0, "decision"), (6000.0, "escalade")])
def test_partenaire_indisponible_le_mode_degrade_depend_du_montant(
    montant: float, issue: str
) -> None:
    d = demande(
        contrat={"date_souscription": "2026-07-01"},  # F2 : contrat récent
        sinistre={"montant_declare": montant},
        pieces=[
            {"type": "facture", "lisible": True, "montant": montant},
            {"type": "photo", "lisible": True},
        ],
    )
    fiche = traiter(d, Consultation(None, "delai", "aucune réponse en 3 s"))
    assert (
        fiche["issue"] == issue and fiche["mode_degrade"] is True and fiche["avis_fraude"] is None
    )
    assert "Avis indisponible" in fiche["rapport"] and "Anti-fraude" not in fiche["rapport_assure"]


def test_au_dela_du_seuil_de_delegation_la_demande_est_escaladee() -> None:
    d = demande(
        contrat={"formule": "premium"},
        sinistre={"montant_declare": 12000.0},
        pieces=[
            {"type": "facture", "lisible": True, "montant": 12000.0},
            {"type": "photo", "lisible": True},
        ],
    )
    fiche = traiter(d)
    assert (fiche["file"], fiche["regle"]) == ("gestionnaire", 5)
    assert "transmis à un gestionnaire" in fiche["rapport_assure"]


# ----------------------------------------------------------- pièces et bornes


def test_sans_depot_de_l_assure_les_pieces_manquent() -> None:
    fiche = traiter(demande(pieces=[{"type": "facture", "lisible": True, "montant": 1800.0}]))
    assert (fiche["file"], fiche["regle"]) == ("gestionnaire", 2)
    assert "manquantes" in fiche["rapport"]


def test_deux_complements_differents_puis_la_borne_complements_max() -> None:
    d = demande(
        pieces=[{"type": "facture", "lisible": True, "montant": 1800.0}],
        espace_assure={
            "depots": [
                {"type": "photo", "lisible": False, "essai": 1},
                {"type": "photo", "lisible": False, "essai": 2},
            ]
        },
    )
    fiche = traiter(d)
    assert fiche["arret"]["borne"] == "complements_max" and fiche["issue"] == "escalade"


def test_la_borne_etapes_max_laisse_toujours_une_etape_pour_conclure() -> None:
    d = demande(
        pieces=[{"type": "facture", "lisible": True, "montant": 1800.0}],
        espace_assure={"depots": [{"type": "photo", "lisible": True}]},
    )
    fiche = traiter(d, etapes_max=3)
    assert fiche["arret"]["borne"] == "etapes_max" and len(fiche["trace"]) <= 3


def test_la_borne_de_duree_interrompt_la_demande() -> None:
    fiche = traiter(demande(), duree_max_s=0)
    assert fiche["arret"]["borne"] == "duree_max_s" and fiche["issue"] == "escalade"
    assert "non examinée" in fiche["rapport"]


# ------------------------------------------------------- filet de sécurité


class AgentFautif:
    nom, section, action = "eligibilite", "eligibilite", "verifier_eligibilite"

    def __init__(self, resultat: Any) -> None:
        self.resultat = resultat

    def traiter(self, vue: dict[str, Any]) -> Resultat:
        if isinstance(self.resultat, Exception):
            raise self.resultat
        return self.resultat


@pytest.mark.parametrize(
    "resultat",
    [RuntimeError("panne interne"), Resultat("conclu", {"eligible": True}), "pas un résultat"],
    ids=["exception", "champ manquant", "type inattendu"],
)
def test_un_agent_defaillant_donne_une_escalade_jamais_un_silence(resultat: Any) -> None:
    superviseur = Superviseur(client=FauxClient(Consultation(None)))  # type: ignore[arg-type]
    superviseur.eligibilite = AgentFautif(resultat)  # type: ignore[assignment]
    fiche = superviseur.traiter(demande())
    assert fiche["issue"] == "escalade" and fiche["arret"]["borne"] == "incident"
    assert fiche["trace"][0]["statut"] == "erreur"


def test_un_agent_indetermine_donne_une_escalade_motivee() -> None:
    superviseur = Superviseur(client=FauxClient(Consultation(None)))  # type: ignore[arg-type]
    superviseur.eligibilite = AgentFautif(Resultat("indetermine", {}, motif="dates illisibles"))  # type: ignore[assignment]
    fiche = superviseur.traiter(demande())
    assert fiche["file"] == "gestionnaire" and "dates illisibles" in fiche["motif"]


def test_l_etat_refuse_une_ecriture_hors_frontiere() -> None:
    etat = Etat(demande())
    with pytest.raises(ViolationFrontiere):
        etat.enregistrer("pieces", "eligibilite", {})
    etat.enregistrer("eligibilite", "eligibilite", {"eligible": True})
    with pytest.raises(ViolationFrontiere):
        etat.enregistrer("eligibilite", "eligibilite", {"eligible": False})


# ------------------------------------------------------- briques isolées


@pytest.mark.parametrize(
    ("args", "estime", "plafond_applique"),
    [
        ((4200.0, [4200.0], 300.0, 3000.0), 3000.0, True),
        ((3100.0, [3100.0], 300.0, 3000.0), 2800.0, False),
        ((25000.0, [15000.0], 0.0, 20000.0), 15000.0, False),
        ((200.0, [200.0], 300.0, 3000.0), 0.0, False),
    ],
)
def test_le_plafond_s_applique_apres_la_franchise(
    args: tuple, estime: float, plafond_applique: bool
) -> None:
    resultat = calculer_montant(*args)
    assert (resultat["montant_estime"], resultat["plafond_applique"]) == (estime, plafond_applique)


@pytest.mark.parametrize(
    ("code", "dep"),
    [("69003", "69"), ("20000", "2A"), ("20200", "2B"), ("97411", "974"), ("98800", "988")],
)
def test_departement_selon_le_contrat(code: str, dep: str) -> None:
    assert departement(code) == dep


def test_decision_sans_pieces_et_format_des_euros() -> None:
    issue = decision.decider({"eligible": True, "motifs": []}, None, None, None)
    assert issue["regle"] == 2 and "non vérifiées" in issue["motif"]
    assert decision.euros(1234.5) == "1 234,50 €"


def test_metriques_par_agent() -> None:
    fiches = [
        {
            "trace": [
                {"agent": "antifraude", "duree_ms": 10.0, "echec": True, "appels_externes": 1},
                {"agent": "antifraude", "duree_ms": 30.0, "appels_externes": 1},
            ]
        }
    ]
    assert metriques.par_agent(fiches) == {
        "antifraude": {
            "appels": 2,
            "echecs": 1,
            "latence_ms": 20.0,
            "appels_externes": 2,
            "anomalies": 0,
        }
    }


def test_traiter_lot_garde_l_ordre_et_accepte_un_lot_vide() -> None:
    assert kaldera.traiter_lot([]) == {"fiches": [], "metriques": {}}
    refs = ["KAL-26-0001", "KAL-26-0002"]
    lot = [demande(reference=r, contrat={"statut": "suspendu"}) for r in refs]
    resultat = kaldera.traiter_lot(lot)
    assert [f["reference"] for f in resultat["fiches"]] == refs
    assert kaldera.bornes()["etapes_max"] == BORNES["etapes_max"]
