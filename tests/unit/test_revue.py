"""Revue de fond du superviseur : un signal noté, compté et rapporté, jamais une correction."""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx
import pytest

from kaldera import llm, metriques, revue
from kaldera.agents import Resultat
from kaldera.agents.estimation import calculer_montant
from kaldera.bornes import BORNES
from kaldera.partenaire import Consultation
from kaldera.revue import RevueLLM, RevueRegles, RevueSystemOne, Signal
from kaldera.superviseur import Superviseur

from fabrique import AVIS_FAIBLE, FauxClient, demande

CHAMPS_FICHE = (
    "issue",
    "decision",
    "montant_rembourse",
    "motif",
    "file",
    "regle",
    "avis_fraude",
    "mode_degrade",
    "arret",
)
DONNEES_PERSONNELLES = ("Martin", "anne.martin", "FR76", "0600000000", "C-001", "Fuite sous")


def nouveau_superviseur(reviseur: Any = "defaut", **bornes: Any) -> Superviseur:
    """Superviseur branché sur un faux partenaire qui rend un avis faible."""
    client: Any = FauxClient(Consultation(dict(AVIS_FAIBLE)))
    return Superviseur(bornes={**BORNES, **bornes}, client=client, reviseur=reviseur)


def traiter(
    d: dict[str, Any] | None = None, reviseur: Any = "defaut", **bornes: Any
) -> dict[str, Any]:
    return nouveau_superviseur(reviseur, **bornes).traiter(d or demande())


def essentiel(fiche: dict[str, Any]) -> dict[str, Any]:
    return {c: fiche[c] for c in CHAMPS_FICHE}


def revues(fiche: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["ecrit"][0]: e["revue"] for e in fiche["trace"] if "revue" in e}


def derniere_ligne(texte: str) -> str:
    return texte.splitlines()[-1]


DEMANDE_AVEC_AVIS = demande(
    sinistre={"montant_declare": 6000.0},
    pieces=[
        {"type": "facture", "lisible": True, "montant": 6000.0},
        {"type": "photo", "lisible": True},
    ],
)


# -------------------------------------------------------- réviseurs factices


class Signaleur:
    """Signale une anomalie sur les sections choisies (toutes à défaut) et garde ce qu'il voit."""

    nom = "factice"

    def __init__(self, sections: set[str] | None = None) -> None:
        self.sections = sections
        self.examens: list[tuple[str, dict[str, Any]]] = []

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        self.examens.append((section, valeur))
        if self.sections is None or section in self.sections:
            return Signal("anomalie", f"désaccord sur {section}")
        return Signal("conforme", "rien à signaler")


class EnPanne:
    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        raise RuntimeError("panne du réviseur")


class Saboteur:
    """Tente de modifier ce qu'il examine : il ne travaille que sur une copie."""

    nom = "saboteur"

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        valeur.update(eligible=False, conformes=False, montant_estime=0.0, statut="obtenu")
        valeur.clear()
        return Signal("conforme", "rien à signaler")


class Lent:
    nom, delai_s = "lent", 0.05

    def __init__(self) -> None:
        self.libere = threading.Event()

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        self.libere.wait(5)
        return Signal("anomalie", "trop tard")


class Fixe:
    def __init__(self, rendu: Any, delai_s: Any = 1.0) -> None:
        self.rendu, self.delai_s = rendu, delai_s

    def examiner(self, section: str, valeur: dict[str, Any]) -> Any:
        return self.rendu


class EstimationFautive:
    """Estimation qui rembourse plus que le montant retenu : la revue le signale, sans corriger."""

    nom = section = "estimation"
    action = "estimer"

    def traiter(self, vue: dict[str, Any]) -> Resultat:
        montants = calculer_montant(
            vue["montant_declare"], vue["factures"], vue["franchise"], vue["plafond"]
        )
        contexte = {k: vue[k] for k in ("formule", "franchise", "montant_declare")}
        return Resultat("conclu", {**contexte, **montants, "montant_estime": 1900.0})


# ------------------------------------------------------------ RevueRegles

ESTIMATION = {
    "formule": "confort",
    "franchise": 150.0,
    "montant_declare": 1800.0,
    "factures": [1800.0],
    **calculer_montant(1800.0, [1800.0], 150.0, 8000.0),
}
ESTIMATION_PLAFONNEE = {
    "formule": "essentiel",
    "franchise": 300.0,
    "montant_declare": 4200.0,
    "factures": [4200.0],
    **calculer_montant(4200.0, [4200.0], 300.0, 3000.0),
}
PIECES = {"conformes": True, "a_redemander": [], "sans_depot": [], "factures": [1800.0]}
AVIS = {
    "statut": "obtenu",
    "indicateurs": ["F1"],
    "niveau": "faible",
    "score": 0.12,
    "evaluation_id": "EVA-1",
}


@pytest.mark.parametrize(
    ("section", "valeur"),
    [
        ("eligibilite", {"eligible": True, "motifs": []}),
        ("eligibilite", {"eligible": False, "motifs": ["contrat non actif"]}),
        ("pieces", PIECES),
        ("pieces", {**PIECES, "conformes": False, "a_redemander": ["photo"]}),
        ("estimation", ESTIMATION),
        ("estimation", ESTIMATION_PLAFONNEE),
        ("estimation", {k: v for k, v in ESTIMATION.items() if k != "factures"}),
        ("estimation", {"factures": [200.0], **calculer_montant(200.0, [200.0], 300.0, 3000.0)}),
        ("avis_fraude", {"statut": "non_requis", "indicateurs": []}),
        ("avis_fraude", AVIS),
        ("avis_fraude", {"statut": "indisponible", "indicateurs": ["F2"], "rejet": {}}),
    ],
)
def test_une_section_coherente_est_conforme(section: str, valeur: dict[str, Any]) -> None:
    assert RevueRegles().examiner(section, valeur).statut == "conforme"


@pytest.mark.parametrize(
    ("section", "valeur", "extrait"),
    [
        ("eligibilite", {"eligible": True, "motifs": ["x"]}, "éligible portant des motifs"),
        ("eligibilite", {"eligible": False, "motifs": []}, "non éligible sans motif"),
        ("pieces", {**PIECES, "a_redemander": ["photo"]}, "conformes alors que"),
        ("pieces", {**PIECES, "conformes": False}, "non conformes sans pièce"),
        ("pieces", {**PIECES, "factures": [-5.0]}, "facture de montant négatif"),
        ("estimation", {**ESTIMATION, "plafond": 1000.0}, "supérieur au plafond"),
        ("estimation", {**ESTIMATION, "montant_estime": 1900.0}, "supérieur au montant retenu"),
        ("estimation", {**ESTIMATION, "factures": [1000.0]}, "somme des factures 1 000,00 €"),
        ("estimation", {**ESTIMATION, "montant_retenu": 1500.0}, "plus petit du déclaré"),
        ("estimation", {**ESTIMATION, "montant_estime": -10.0}, "montant estimé négatif"),
        ("estimation", {**ESTIMATION, "plafond_applique": True}, "ne le dépasse pas"),
        (
            "estimation",
            {**ESTIMATION_PLAFONNEE, "montant_estime": 2900.0},
            "différent du plafond",
        ),
        ("estimation", {**ESTIMATION_PLAFONNEE, "plafond_applique": False}, "non signalé"),
        ("avis_fraude", {"statut": "non_requis", "indicateurs": ["F1"]}, "malgré des indicateurs"),
        ("avis_fraude", {**AVIS, "indicateurs": []}, "sans indicateur"),
        ("avis_fraude", {**AVIS, "score": 1.4}, "hors de l'intervalle"),
        ("avis_fraude", {**AVIS, "score": 0.9}, "incohérent avec son score"),
        ("avis_fraude", {**AVIS, "statut": "rembourser"}, "statut d'avis inconnu"),
    ],
)
def test_chaque_controle_de_fond_signale_son_anomalie(
    section: str, valeur: dict[str, Any], extrait: str
) -> None:
    signal = RevueRegles().examiner(section, valeur)
    assert signal.statut == "anomalie" and extrait in signal.raison
    assert signal.confiance is None


@pytest.mark.parametrize(
    ("section", "valeur", "extrait"),
    [
        ("issue", {"issue": "decision"}, "aucun contrôle"),
        ("eligibilite", {"eligible": True}, "incomplète ou mal typée"),
        ("eligibilite", {"eligible": "oui", "motifs": []}, "incomplète ou mal typée"),
        ("pieces", {**PIECES, "a_redemander": "photo"}, "incomplète ou mal typée"),
        ("estimation", {**ESTIMATION, "montant_estime": "1650"}, "incomplète ou mal typée"),
    ],
)
def test_une_section_inconnue_ou_mal_formee_est_indeterminee(
    section: str, valeur: dict[str, Any], extrait: str
) -> None:
    signal = RevueRegles().examiner(section, valeur)
    assert signal.statut == "indetermine" and extrait in signal.raison


# ------------------------------------------------------ dans le superviseur


def test_le_reviseur_par_defaut_examine_chaque_section_sans_rien_signaler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(revue.VARIABLE_REVUE, raising=False)
    fiche = traiter(DEMANDE_AVEC_AVIS)
    examens = revues(fiche)
    assert set(examens) == {"eligibilite", "pieces", "estimation", "avis_fraude"}
    assert {(r["reviseur"], r["statut"]) for r in examens.values()} == {("regles", "conforme")}
    assert "issue" not in examens and all(r["duree_ms"] >= 0 for r in examens.values())
    assert derniere_ligne(fiche["rapport"]) == "Revue de fond : aucune anomalie."
    assert all(m["anomalies"] == 0 for m in metriques.par_agent([fiche]).values())


def test_une_anomalie_est_signalee_sans_changer_l_issue() -> None:
    signaleur = Signaleur({"estimation"})
    fiche = traiter(reviseur=signaleur)
    assert essentiel(fiche) == essentiel(traiter(reviseur=None))
    assert (fiche["decision"], fiche["montant_rembourse"]) == ("acceptee", 1650.0)
    assert revues(fiche)["estimation"] == {
        "reviseur": "factice",
        "statut": "anomalie",
        "raison": "désaccord sur estimation",
        "confiance": None,
        "duree_ms": revues(fiche)["estimation"]["duree_ms"],
    }
    assert derniere_ligne(fiche["rapport"]) == (
        "Revue de fond : 1 anomalie signalée (estimation : désaccord sur estimation)"
        " — signal seul : aucune valeur modifiée, issue inchangée."
    )
    assert "Revue" not in fiche["rapport_assure"]
    compte = {a: m["anomalies"] for a, m in metriques.par_agent([fiche]).items()}
    assert compte == {
        "eligibilite": 0,
        "pieces": 0,
        "estimation": 1,
        "antifraude": 0,
        "superviseur": 0,
    }
    # L'estimation est examinée avec les factures sur lesquelles elle a été calculée.
    assert dict(signaleur.examens)["estimation"]["factures"] == [1800.0]


def test_plusieurs_anomalies_sont_toutes_rapportees() -> None:
    fiche = traiter(reviseur=Signaleur())
    assert essentiel(fiche) == essentiel(traiter(reviseur=None))
    assert "Revue de fond : 4 anomalies signalées (eligibilite" in fiche["rapport"]


def test_en_desaccord_le_sous_agent_a_raison() -> None:
    def avec_estimation_fautive(reviseur: Any) -> dict[str, Any]:
        superviseur = nouveau_superviseur(reviseur)
        superviseur.estimation = EstimationFautive()  # type: ignore[assignment]
        return superviseur.traiter(demande())

    fiche = avec_estimation_fautive(RevueRegles())
    assert essentiel(fiche) == essentiel(avec_estimation_fautive(None))
    assert fiche["montant_rembourse"] == 1900.0  # la valeur de l'agent, non corrigée
    assert revues(fiche)["estimation"]["statut"] == "anomalie"
    assert "supérieur au montant retenu" in derniere_ligne(fiche["rapport"])


def test_un_reviseur_en_panne_n_affecte_pas_le_traitement() -> None:
    fiche = traiter(reviseur=EnPanne())
    assert essentiel(fiche) == essentiel(traiter(reviseur=None)) and fiche["arret"] is None
    for examen in revues(fiche).values():
        assert examen["statut"] == "indisponible" and "RuntimeError" in examen["raison"]
        assert examen["reviseur"] == "EnPanne"
    assert derniere_ligne(fiche["rapport"]) == (
        "Revue de fond : aucune anomalie (4 examen(s) non concluant(s))."
    )


def test_un_reviseur_ne_peut_modifier_aucune_valeur() -> None:
    fiche = traiter(DEMANDE_AVEC_AVIS, reviseur=Saboteur())
    assert essentiel(fiche) == essentiel(traiter(DEMANDE_AVEC_AVIS, reviseur=None))
    assert fiche["decision"] == "acceptee" and fiche["avis_fraude"]["niveau"] == "faible"


def test_un_reviseur_trop_lent_n_est_pas_attendu() -> None:
    lent = Lent()
    try:
        fiche = traiter(reviseur=lent)
    finally:
        lent.libere.set()
    assert essentiel(fiche) == essentiel(traiter(reviseur=None))
    examens = revues(fiche).values()
    assert {r["statut"] for r in examens} == {"indisponible"}
    assert all("non rendue" in r["raison"] and r["duree_ms"] < 1000 for r in examens)


def test_la_revue_ne_prend_jamais_le_temps_reserve_au_traitement() -> None:
    signaleur = Signaleur()
    fiche = traiter(reviseur=signaleur, duree_max_s=BORNES["delai_partenaire_s"] + 0.5)
    assert essentiel(fiche) == essentiel(traiter(reviseur=None)) and not signaleur.examens
    examens = revues(fiche).values()
    assert len(examens) == 4 and all("budget" in r["raison"] for r in examens)


def test_sans_reviseur_aucune_revue_n_est_notee() -> None:
    fiche = traiter(reviseur=None)
    assert not revues(fiche)
    assert derniere_ligne(fiche["rapport"]) == "Revue de fond : non effectuée."


def test_une_section_indeterminee_n_est_pas_examinee() -> None:
    class Indetermine:
        nom, section, action = "eligibilite", "eligibilite", "verifier_eligibilite"

        def traiter(self, vue: dict[str, Any]) -> Resultat:
            return Resultat("indetermine", {}, motif="dates illisibles")

    signaleur = Signaleur()
    superviseur = nouveau_superviseur(signaleur)
    superviseur.eligibilite = Indetermine()  # type: ignore[assignment]
    fiche = superviseur.traiter(demande())
    assert fiche["issue"] == "escalade" and "revue" not in fiche["trace"][0]
    assert not signaleur.examens


# ------------------------------------------------------- exécution bornée


@pytest.mark.parametrize(
    ("reviseur", "extrait"),
    [
        (Fixe("pas un signal"), "non conforme"),
        (Fixe(Signal("peut-etre", "x")), "non conforme"),  # type: ignore[arg-type]
        (Fixe(Signal("conforme", "x", confiance=1.7)), "non conforme"),
        (Fixe(Signal("conforme", 42)), "non conforme"),  # type: ignore[arg-type]
    ],
)
def test_un_signal_non_conforme_devient_indisponible(reviseur: Any, extrait: str) -> None:
    entree = revue.reviser(reviseur, "pieces", PIECES, budget_s=1.0)
    assert entree["statut"] == "indisponible" and extrait in entree["raison"]
    assert entree["reviseur"] == "Fixe"


def test_une_raison_trop_longue_est_abregee_sur_une_ligne() -> None:
    reviseur = Fixe(Signal("anomalie", "a\nb " * 200, confiance=0.9), delai_s="vite")
    entree = revue.reviser(reviseur, "pieces", PIECES, budget_s=1.0)
    assert len(entree["raison"]) == revue.LONGUEUR_RAISON_MAX and entree["raison"].endswith("…")
    assert "\n" not in entree["raison"] and entree["confiance"] == 0.9


def test_les_entrees_jointes_ne_remplacent_jamais_un_champ_de_la_section() -> None:
    def lire(section: str) -> Any:
        return {"factures": [9.0]} if section == "pieces" else None

    assert revue.a_examiner("estimation", {"factures": [1.0]}, lire) == {"factures": [1.0]}
    assert revue.a_examiner("estimation", {}, lambda s: None) == {}
    assert revue.a_examiner("pieces", PIECES, lire) == PIECES


def test_une_erreur_avant_l_examen_devient_indisponible() -> None:
    def lire(section: str) -> Any:
        raise RuntimeError("état illisible")

    entree = revue.reviser(RevueRegles(), "estimation", ESTIMATION, budget_s=1.0, lire=lire)
    assert entree["statut"] == "indisponible" and "RuntimeError" in entree["raison"]
    assert entree["reviseur"] == "regles"


# --------------------------------------------------------------- RevueLLM


class FauxModele:
    def __init__(self, reponse: Any) -> None:
        self.reponse = reponse
        self.messages: list[Any] = []

    def invoke(self, messages: Any) -> Any:
        self.messages.append(messages)
        if isinstance(self.reponse, BaseException):
            raise self.reponse
        return self.reponse


class Message:
    def __init__(self, content: Any) -> None:
        self.content = content


def brancher(monkeypatch: pytest.MonkeyPatch, reponse: Any) -> FauxModele:
    modele = FauxModele(reponse)
    monkeypatch.setattr(llm, "get_llm", lambda: modele)
    return modele


def test_revue_llm_lit_une_reponse_valide_et_ne_transmet_que_la_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contenu = '```json\n{"statut": "anomalie", "raison": "score et niveau discordants"}\n```'
    modele = brancher(monkeypatch, Message(contenu))
    signal = RevueLLM().examiner("avis_fraude", {**AVIS, "rejet": {"raison": "x"}})
    assert signal == Signal("anomalie", "score et niveau discordants")
    (systeme, humain), *_ = modele.messages
    assert systeme[0] == "system" and "JSON" in systeme[1]
    assert json.loads(humain[1]) == {
        "section": "avis_fraude",
        "valeur": {"statut": "obtenu", "indicateurs": ["F1"], "niveau": "faible", "score": 0.12},
    }


@pytest.mark.parametrize(
    "contenu",
    [
        "Tout me semble cohérent.",
        '{"statut": "ok", "raison": "x"}',
        '{"statut": "indisponible", "raison": "x"}',
        '{"statut": "conforme"}',
        "{statut: conforme}",
        '["conforme"]',
        ["conforme"],
    ],
)
def test_revue_llm_une_reponse_illisible_est_indisponible(
    monkeypatch: pytest.MonkeyPatch, contenu: Any
) -> None:
    brancher(monkeypatch, Message(contenu))
    assert RevueLLM().examiner("pieces", PIECES) == Signal(
        "indisponible", "réponse du modèle illisible"
    )


@pytest.mark.parametrize(
    ("erreur", "extrait"),
    [
        (RuntimeError("quota"), "RuntimeError"),
        (TimeoutError(), "aucune réponse dans le délai"),
        (httpx.ReadTimeout("lent"), "aucune réponse dans le délai"),
    ],
)
def test_revue_llm_une_erreur_est_indisponible(
    monkeypatch: pytest.MonkeyPatch, erreur: BaseException, extrait: str
) -> None:
    brancher(monkeypatch, erreur)
    signal = RevueLLM().examiner("pieces", PIECES)
    assert signal.statut == "indisponible" and extrait in signal.raison


def test_revue_llm_sans_modele_configure_est_indisponible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def absent() -> Any:
        raise KeyError("AZURE_OPENAI_ENDPOINT")

    monkeypatch.setattr(llm, "get_llm", absent)
    signal = RevueLLM(delai_s=0.5).examiner("pieces", PIECES)
    assert signal.statut == "indisponible" and "KeyError" in signal.raison


def test_revue_llm_une_section_sans_champ_transmissible_est_indeterminee() -> None:
    assert RevueLLM().examiner("issue", {"motif": "x"}).statut == "indetermine"


def test_revue_llm_dans_le_superviseur_ne_voit_aucune_donnee_personnelle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modele = brancher(monkeypatch, Message('{"statut": "conforme", "raison": "cohérent"}'))
    appels: list[int] = []
    monkeypatch.setattr(llm, "get_llm", lambda: appels.append(1) or modele)
    fiche = traiter(DEMANDE_AVEC_AVIS, reviseur=RevueLLM())
    assert essentiel(fiche) == essentiel(traiter(DEMANDE_AVEC_AVIS, reviseur=None))
    assert {(r["reviseur"], r["statut"]) for r in revues(fiche).values()} == {("llm", "conforme")}
    assert len(appels) == 1 and len(modele.messages) == 4  # un modèle, un appel par section
    envoye = json.dumps(modele.messages, ensure_ascii=False)
    assert not [d for d in DONNEES_PERSONNELLES if d in envoye]
    assert "EVA-1" not in envoye and "KAL-26-9001" not in envoye


# --------------------------------------------------------- RevueSystemOne


def faux_post(reponse: Any, appels: list[dict[str, Any]]) -> Any:
    def post(url: str, **options: Any) -> Any:
        appels.append({"url": url, **options})
        if isinstance(reponse, BaseException):
            raise reponse
        return reponse

    return post


@pytest.fixture
def system_one(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setenv(revue.VARIABLE_URL, "https://system-one.test/decider")
    monkeypatch.setenv(revue.VARIABLE_CLE, "cle-de-test")
    monkeypatch.delenv(revue.VARIABLE_SEUIL, raising=False)
    return []


def repondre(monkeypatch: pytest.MonkeyPatch, appels: list[dict[str, Any]], reponse: Any) -> None:
    monkeypatch.setattr(revue.httpx, "post", faux_post(reponse, appels))


def test_system_one_confiance_haute_le_verdict_est_retenu(
    monkeypatch: pytest.MonkeyPatch, system_one: list[dict[str, Any]]
) -> None:
    repondre(
        monkeypatch, system_one, httpx.Response(200, json={"statut": "anomalie", "confiance": 0.93})
    )
    signal = RevueSystemOne().examiner("avis_fraude", AVIS)
    assert (signal.statut, signal.confiance) == ("anomalie", 0.93)
    assert "confiance 0.93" in signal.raison
    (appel,) = system_one
    assert appel["url"] == "https://system-one.test/decider" and appel["timeout"] == 1.0
    assert appel["headers"] == {"Authorization": "Bearer cle-de-test"}
    assert appel["json"]["valeur"] == {
        k: AVIS[k] for k in ("statut", "indicateurs", "niveau", "score")
    }
    assert appel["json"]["sorties"] == ["conforme", "anomalie", "indetermine"]


def test_system_one_confiance_basse_donne_indetermine(
    monkeypatch: pytest.MonkeyPatch, system_one: list[dict[str, Any]]
) -> None:
    repondre(
        monkeypatch, system_one, httpx.Response(200, json={"statut": "anomalie", "confiance": 0.42})
    )
    signal = RevueSystemOne().examiner("estimation", ESTIMATION)
    assert (signal.statut, signal.confiance) == ("indetermine", 0.42)
    assert "sous le seuil 0.80" in signal.raison
    assert "factures" not in system_one[0]["json"]["valeur"]  # la section seule


@pytest.mark.parametrize(
    ("reponse", "extrait"),
    [
        (httpx.ConnectError("refus"), "injoignable (ConnectError)"),
        (httpx.ReadTimeout("lent"), "aucune réponse en 1 s"),
        (httpx.Response(503, content=b"{}"), "statut HTTP 503"),
        (httpx.Response(200, content=b"<html>"), "réponse illisible"),
        (httpx.Response(200, json=[1, 2]), "réponse illisible"),
        (httpx.Response(200, json={"statut": "conforme", "confiance": 1.7}), "réponse illisible"),
        (httpx.Response(200, json={"statut": "conforme", "confiance": True}), "réponse illisible"),
        (httpx.Response(200, json={"statut": "peut-etre", "confiance": 0.9}), "réponse illisible"),
    ],
)
def test_system_one_une_erreur_est_indisponible(
    monkeypatch: pytest.MonkeyPatch,
    system_one: list[dict[str, Any]],
    reponse: Any,
    extrait: str,
) -> None:
    repondre(monkeypatch, system_one, reponse)
    signal = RevueSystemOne().examiner("pieces", PIECES)
    assert signal.statut == "indisponible" and extrait in signal.raison


def test_system_one_sans_url_n_appelle_personne(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(revue.VARIABLE_URL, raising=False)
    appels: list[dict[str, Any]] = []
    repondre(monkeypatch, appels, httpx.Response(200, json={}))
    signal = RevueSystemOne().examiner("pieces", PIECES)
    assert signal.statut == "indisponible" and revue.VARIABLE_URL in signal.raison and not appels


@pytest.mark.parametrize(
    ("brut", "seuil"), [("0,95", 0.95), ("0.6", 0.6), ("abc", 0.8), ("1.5", 0.8), ("", 0.8)]
)
def test_le_seuil_de_confiance_se_regle_par_l_environnement(
    monkeypatch: pytest.MonkeyPatch, brut: str, seuil: float
) -> None:
    monkeypatch.setenv(revue.VARIABLE_SEUIL, brut)
    assert RevueSystemOne(url="http://x").seuil == seuil


def test_system_one_respecte_un_seuil_plus_exigeant(
    monkeypatch: pytest.MonkeyPatch, system_one: list[dict[str, Any]]
) -> None:
    monkeypatch.setenv(revue.VARIABLE_SEUIL, "0.97")
    repondre(
        monkeypatch, system_one, httpx.Response(200, json={"statut": "conforme", "confiance": 0.95})
    )
    assert RevueSystemOne(delai_s=0.5).examiner("pieces", PIECES).statut == "indetermine"
    assert system_one[0]["timeout"] == 0.5


# ---------------------------------------------------------------- choix


@pytest.mark.parametrize(
    ("choix", "attendu"),
    [
        (None, RevueRegles),
        ("regles", RevueRegles),
        ("", RevueRegles),
        ("inconnu", RevueRegles),
        ("aucune", type(None)),
        ("llm", RevueLLM),
        ("system_one", RevueSystemOne),
        (" System-One ", RevueSystemOne),
    ],
)
def test_choisir_reviseur_selon_kaldera_revue(
    monkeypatch: pytest.MonkeyPatch, choix: str | None, attendu: type
) -> None:
    if choix is None:
        monkeypatch.delenv(revue.VARIABLE_REVUE, raising=False)
    else:
        monkeypatch.setenv(revue.VARIABLE_REVUE, choix)
    assert type(revue.choisir_reviseur()) is attendu
    assert type(nouveau_superviseur().reviseur) is attendu


def test_un_choix_explicite_l_emporte_sur_l_environnement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(revue.VARIABLE_REVUE, "aucune")
    assert isinstance(revue.choisir_reviseur("regles"), RevueRegles)


# ------------------------------------------------------------- métriques


def test_les_metriques_comptent_les_anomalies_par_agent() -> None:
    fiches = [
        {
            "trace": [
                {"agent": "estimation", "duree_ms": 1.0, "revue": {"statut": "anomalie"}},
                {"agent": "estimation", "duree_ms": 1.0, "revue": {"statut": "conforme"}},
                {"agent": "pieces", "duree_ms": 1.0, "revue": {"statut": "indisponible"}},
                {"agent": "superviseur", "duree_ms": 1.0},
            ]
        },
        {"trace": [{"agent": "estimation", "duree_ms": 1.0, "revue": {"statut": "anomalie"}}]},
    ]
    compte = {a: m["anomalies"] for a, m in metriques.par_agent(fiches).items()}
    assert compte == {"estimation": 2, "pieces": 0, "superviseur": 0}
