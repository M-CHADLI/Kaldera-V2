"""Cas de test de bout en bout (exemples/cas/) : la variante A est extraite puis traitée.

Les résultats attendus (attendu.json) ont été établis avec le vrai pipeline et le partenaire
anti-fraude maison. Ici, sans réseau ni modèle, le partenaire est remplacé par un faux qui
reproduit sa règle de score ; la variante B (texte libre, qui exige un modèle) est seulement
vérifiée : PDF lisibles, aucune ligne « Libellé : valeur », mêmes pièces que la variante A.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

import kaldera
from kaldera import extraction as ex
from kaldera import partenaire, vues
from kaldera.partenaire import Consultation
from partenaire_antifraude import app as partenaire_maison

from fabrique import sans_modele

RACINE = Path(__file__).resolve().parents[2] / "exemples" / "cas"
ATTENDU: dict[str, dict[str, Any]] = json.loads((RACINE / "attendu.json").read_text("utf-8"))
CAS = sorted(ATTENDU)
VARIANTES = ("A-etiquete", "B-libre")
SIGNATURE_PNG = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])
ROLES = (
    ("contrat", "contrat"),
    ("declaration-sinistre", "declaration"),
    ("facture-", "facture"),
    ("photo-", "photo"),
    ("depot-de-plainte", "plainte"),
)


def documents(dossier: Path, roles: tuple[str, ...] | None = None) -> list[ex.Document]:
    """Les fichiers d'un dossier dans l'ordre de dépôt (préfixe numérique), avec leur rôle."""
    resultat = []
    for chemin in sorted(dossier.iterdir(), key=lambda c: int(c.name.split("-", 1)[0])):
        reste = chemin.name.split("-", 1)[1]
        role = next(r for debut, r in ROLES if reste.startswith(debut))
        if roles is None or role in roles:
            resultat.append(ex.Document(role, chemin.name, chemin.read_bytes()))
    return resultat


def analyser_a(cas: str) -> ex.Analyse:
    return ex.analyser_documents(documents(RACINE / cas / VARIANTES[0]), [ex.ExtracteurChamps()])


# ------------------------------------------------------- faux partenaire anti-fraude

POIDS = {
    "MONTANT_ELEVE": 0.22,
    "SINISTRE_PRECOCE": 0.18,
    "FREQUENCE_ELEVEE": 0.30,
    "TYPE_SENSIBLE": 0.12,
}


def avis_du_faux_partenaire(donnees: dict[str, Any]) -> dict[str, Any]:
    """La règle de score du partenaire : 0,06 + poids des indicateurs ; < 0,40 faible, < 0,75 modéré."""
    indicateurs = []
    if donnees["montant_declare"] >= 5000:
        indicateurs.append("MONTANT_ELEVE")
    if donnees["anciennete_contrat_jours"] < 90:
        indicateurs.append("SINISTRE_PRECOCE")
    if donnees["sinistres_12_mois"] >= 3:
        indicateurs.append("FREQUENCE_ELEVEE")
    if donnees["type_sinistre"] == "vol":
        indicateurs.append("TYPE_SENSIBLE")
    score = round(0.06 + sum(POIDS[i] for i in indicateurs), 2)
    return {
        "reference_dossier": donnees["reference_dossier"],
        "score": score,
        "niveau": "faible" if score < 0.40 else "modere" if score < 0.75 else "eleve",
        "indicateurs": indicateurs,
        "evaluation_id": "EVA-faux",
        "version_modele": "faux-1.0",
    }


@pytest.fixture
def appels(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Aucun réseau, aucun modèle ; le faux partenaire note chaque appel et refuse un doublon."""
    sans_modele(monkeypatch)
    monkeypatch.setenv("KALDERA_REVUE", "aucune")
    monkeypatch.delenv("KALDERA_HISTORIQUE", raising=False)
    monkeypatch.delenv("KALDERA_EXTRACTION", raising=False)
    recus: list[dict[str, Any]] = []

    def consulter(donnees: dict[str, Any], url: str, delai_s: float) -> Consultation:
        assert set(donnees) == set(partenaire.CHAMPS_REQUETE)  # les 7 champs du contrat
        assert donnees["reference_dossier"] not in {d["reference_dossier"] for d in recus}
        recus.append(donnees)
        return Consultation(avis_du_faux_partenaire(donnees))

    monkeypatch.setattr(partenaire, "consulter", consulter)
    return recus


@pytest.mark.parametrize(
    ("donnees", "score", "niveau"),
    [
        ({}, 0.06, "faible"),
        ({"montant_declare": 5000}, 0.28, "faible"),
        ({"montant_declare": 5000, "anciennete_contrat_jours": 60}, 0.46, "modere"),
        ({"type_sinistre": "vol", "sinistres_12_mois": 3}, 0.48, "modere"),
        (
            {"montant_declare": 5000, "anciennete_contrat_jours": 60, "sinistres_12_mois": 3},
            0.76,
            "eleve",
        ),
        (
            {
                "montant_declare": 7200,
                "anciennete_contrat_jours": 82,
                "sinistres_12_mois": 3,
                "type_sinistre": "vol",
            },
            0.88,
            "eleve",
        ),
    ],
)
def test_le_faux_partenaire_applique_la_regle_de_score(
    donnees: dict[str, Any], score: float, niveau: str
) -> None:
    complet = {
        "reference_dossier": "KAL-26-0001",
        "type_sinistre": "degat_des_eaux",
        "montant_declare": 2000.0,
        "date_survenance": "2026-09-01",
        "anciennete_contrat_jours": 400,
        "sinistres_12_mois": 0,
        "departement": "69",
        **donnees,
    }
    for avis in (avis_du_faux_partenaire(complet), partenaire_maison.evaluer(complet)):
        assert (avis["score"], avis["niveau"]) == (score, niveau)


# ------------------------------------------------------------------ variante A


@pytest.mark.parametrize("cas", CAS)
def test_variante_a_extraite_puis_traitee_comme_attendu(
    cas: str, appels: list[dict[str, Any]]
) -> None:
    attendu = ATTENDU[cas]
    analyse = analyser_a(cas)
    assert analyse.pret and analyse.demande["reference"] == attendu["reference"]
    assert not any("générée" in note for note in analyse.a_verifier)

    fiche = kaldera.traiter_demande(analyse.demande)
    avis = fiche["avis_fraude"]
    obtenu = {
        "issue": fiche["issue"],
        "decision": fiche["decision"],
        "montant_rembourse": fiche["montant_rembourse"],
        "file": fiche["file"],
        "mode_degrade": fiche["mode_degrade"],
        "avis_fraude": avis["niveau"] if avis else None,
        "score_fraude": avis["score"] if avis else None,
    }
    assert obtenu == {cle: attendu[cle] for cle in obtenu}
    assert fiche["arret"] is None
    assert all(fragment in fiche["motif"] for fragment in attendu["motif_contient"])
    # Le partenaire n'est consulté que si un indicateur de risque l'exige : il a alors rendu un avis.
    assert bool(appels) == (attendu["avis_fraude"] is not None)


@pytest.mark.parametrize("cas", CAS)
def test_le_faux_partenaire_reproduit_le_partenaire_maison(cas: str) -> None:
    donnees = vues.champs_contrat(analyser_a(cas).demande)
    faux, reel = avis_du_faux_partenaire(donnees), partenaire_maison.evaluer(donnees)
    assert (faux["score"], faux["niveau"], faux["indicateurs"]) == (
        reel["score"],
        reel["niveau"],
        reel["indicateurs"],
    )


# ------------------------------------------------------------------- dossiers


def test_chaque_cas_a_ses_deux_variantes_aux_memes_fichiers_et_sa_reference() -> None:
    assert sorted(p.name for p in RACINE.iterdir() if p.is_dir()) == CAS
    assert len(CAS) >= 8
    references = [attendu["reference"] for attendu in ATTENDU.values()]
    assert len(set(references)) == len(references)
    assert all(re.fullmatch(r"KAL-26-\d{4}", r) for r in references)
    for cas in CAS:
        noms = [sorted(p.name for p in (RACINE / cas / v).iterdir()) for v in VARIANTES]
        assert noms[0] == noms[1]
        assert all(re.match(r"\d-(contrat|declaration|facture|photo|depot)", n) for n in noms[0])
        assert [n[0] for n in noms[0]] == [str(i) for i in range(1, len(noms[0]) + 1)]


@pytest.mark.parametrize("variante", VARIANTES)
@pytest.mark.parametrize("cas", CAS)
def test_les_pdf_sont_lisibles_et_les_photos_sont_de_vraies_images(cas: str, variante: str) -> None:
    scannes = ATTENDU[cas]["fichiers_scannes"]
    for chemin in sorted((RACINE / cas / variante).iterdir()):
        octets = chemin.read_bytes()
        if chemin.suffix == ".png":
            assert octets.startswith(SIGNATURE_PNG) and len(octets) > 1024
        elif chemin.name in scannes:
            with pytest.raises(ex.PdfInvalide, match="aucun texte"):
                ex.lire_pdf(octets)
        else:
            texte, _ = ex.lire_pdf(octets)
            assert len(texte.strip()) > 100


@pytest.mark.parametrize("cas", CAS)
def test_variante_b_n_a_aucune_ligne_etiquetee_et_cite_la_reference(cas: str) -> None:
    for variante, attendues in (("A-etiquete", True), ("B-libre", False)):
        textes = documents(RACINE / cas / variante, ("contrat", "declaration"))
        for document in textes:
            champs = ex.ExtracteurChamps().extraire(ex.lire_pdf(document.octets)[0]).champs
            assert bool(champs) is attendues, document.nom
    declaration = documents(RACINE / cas / "B-libre", ("declaration",))[0]
    assert ATTENDU[cas]["reference"] in ex.lire_pdf(declaration.octets)[0]


@pytest.mark.parametrize("cas", CAS)
def test_variante_b_a_les_memes_pieces_que_la_variante_a(cas: str) -> None:
    """Factures, photos et plaintes sont lues sans modèle : même liste, mêmes montants."""
    pieces = []
    for variante in VARIANTES:
        lues = documents(RACINE / cas / variante, ("facture", "photo", "plainte"))
        analyse = ex.analyser_documents(lues, [ex.ExtracteurChamps()])
        pieces.append(analyse.demande["pieces"])
    assert pieces[0] == pieces[1]
    assert any(p["type"] == "facture" for p in pieces[0])
    assert all("montant" in p for p in pieces[1] if p["type"] == "facture" and p["lisible"])


def test_le_generateur_reproduit_les_dossiers_versionnes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("PIL")
    script = Path(__file__).resolve().parents[2] / "scripts" / "generer_cas_exemples.py"
    spec = importlib.util.spec_from_file_location("generer_cas_exemples", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "generer_cas_exemples", module)
    spec.loader.exec_module(module)
    module.generer(tmp_path)

    def fichiers(racine: Path) -> set[str]:
        return {
            p.relative_to(racine).as_posix()
            for p in racine.rglob("*")
            if p.is_file() and p.name not in ("README.md", "attendu.json")
        }

    assert fichiers(tmp_path) == fichiers(RACINE)
    scannes = {f for attendu in ATTENDU.values() for f in attendu["fichiers_scannes"]}
    for relatif in sorted(fichiers(RACINE)):
        if relatif.endswith(".pdf") and relatif.rsplit("/", 1)[-1] not in scannes:
            neuf = ex.lire_pdf((tmp_path / relatif).read_bytes())[0]
            assert neuf == ex.lire_pdf((RACINE / relatif).read_bytes())[0], relatif
