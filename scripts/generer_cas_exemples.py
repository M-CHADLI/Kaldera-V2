"""Génère les dossiers de cas de test de bout en bout (exemples/cas/), aux données fictives.

    uv run python scripts/generer_cas_exemples.py             # écrit exemples/cas/
    uv run python scripts/generer_cas_exemples.py --attendu   # + rejoue le vrai pipeline
    uv run python scripts/generer_cas_exemples.py --tableau   # tableau récapitulatif (Markdown)

Chaque cas existe en deux variantes, avec les mêmes faits :

- ``A-etiquete`` : documents « Libellé : valeur », lus par l'extracteur déterministe ;
- ``B-libre`` : courrier, contrat en phrases, facture avec lignes et TVA, sans ligne étiquetée
  exploitable ; ils demandent l'extraction par modèle (``KALDERA_EXTRACTION=llm``).

Les résultats attendus ne sont pas écrits à la main : ``--attendu`` extrait la variante A de
chaque cas, la traite avec le vrai pipeline et enregistre ce qu'il a décidé dans
``attendu.json``. Il exige un partenaire anti-fraude joignable, lancé à part et redémarré entre
deux passes, car il refuse un second avis pour la même référence :

    PARTENAIRE_JETON=jeton-de-cas uv run uvicorn partenaire_antifraude.app:app --port 8211
    PARTENAIRE_JETON=jeton-de-cas PARTENAIRE_URL=http://127.0.0.1:8211 \\
        uv run python scripts/generer_cas_exemples.py --attendu

Les fichiers générés sont reproductibles : PDF à métadonnées invariantes, images déterministes.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RACINE = Path(__file__).resolve().parents[1] / "exemples" / "cas"
VARIANTES = ("A-etiquete", "B-libre")
AUTEUR = "Kaldera V2 (données fictives)"
MARGE = 56

MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
NOMBRES = {1: "un", 2: "deux", 3: "trois", 4: "quatre"}
FORMULES = {
    "essentiel": (300, 3_000, "qui couvre les dégâts des eaux et les incendies"),
    "confort": (
        150,
        8_000,
        "qui couvre les dégâts des eaux, les incendies, les bris de glace et les vols",
    ),
    "premium": (
        0,
        20_000,
        "qui couvre les dégâts des eaux, les incendies, les bris de glace et les vols",
    ),
}
TYPES = {
    "degat_des_eaux": ("Dégât des eaux", "un dégât des eaux", "eau"),
    "incendie": ("Incendie", "un incendie", "feu"),
    "bris_de_glace": ("Bris de glace", "un bris de glace", "verre"),
    "vol": ("Vol", "un vol avec effraction", "effraction"),
}


# --------------------------------------------------------------------------------- données


@dataclass(frozen=True)
class Assure:
    prenom: str
    nom: str
    feminin: bool
    id_client: str
    email: str
    telephone: str
    iban: str
    rue: str
    code_postal: str
    ville: str

    @property
    def adresse(self) -> str:
        return f"{self.rue}, {self.code_postal} {self.ville}"

    @property
    def civilite(self) -> str:
        return "Madame" if self.feminin else "Monsieur"

    @property
    def e(self) -> str:
        return "e" if self.feminin else ""


@dataclass(frozen=True)
class Ligne:
    designation: str
    quantite: int
    prix_ht: float

    @property
    def total_ht(self) -> float:
        return round(self.quantite * self.prix_ht, 2)


@dataclass(frozen=True)
class Facture:
    fournisseur: str
    slug: str
    adresse: str
    numero: str
    date: date
    lignes: tuple[Ligne, ...]
    taux_tva: float
    scannee: bool = False

    @property
    def total_ht(self) -> float:
        return round(sum(ligne.total_ht for ligne in self.lignes), 2)

    @property
    def tva(self) -> float:
        return round(self.total_ht * self.taux_tva, 2)

    @property
    def total_ttc(self) -> float:
        return round(self.total_ht + self.tva, 2)


@dataclass(frozen=True)
class Plainte:
    commissariat: str
    numero: str
    date: date


@dataclass(frozen=True)
class Cas:
    dossier: str
    titre: str
    eprouve: str
    reference: str
    assure: Assure
    numero_contrat: str
    formule: str
    souscription: date
    statut: str
    cotisations_a_jour: bool
    type_sinistre: str
    survenance: date
    declaration: date
    montant_declare: float
    description: str
    circonstances: str
    factures: tuple[Facture, ...]
    photo: str | None
    sinistres_12_mois: int = 0
    plainte: Plainte | None = None
    date_resiliation: date | None = None
    precision_montant: str = ""
    motif_contient: tuple[str, ...] = field(default_factory=tuple)


def _assure(
    n: int, prenom: str, nom: str, feminin: bool, rue: str, code_postal: str, ville: str
) -> Assure:
    sans_accent = str.maketrans("éèêëàâîïôöûüç", "eeeeaaiioouuc")
    courriel = f"{prenom}.{nom}".lower().translate(sans_accent).replace(" ", "-")
    return Assure(
        prenom=prenom,
        nom=nom,
        feminin=feminin,
        id_client=f"C-{50210 + n}",
        email=f"{courriel}@example.org",
        telephone=f"06 39 98 {10 + n:02d} {20 + n:02d}",
        iban=f"FR76 3000 6000 01{n:02d} 3456 7890 1{n:02d}",
        rue=rue,
        code_postal=code_postal,
        ville=ville,
    )


def _facture(
    fournisseur: str,
    slug: str,
    adresse: str,
    numero: str,
    jour: date,
    lignes: list[tuple[str, int, float]],
    taux: float,
    scannee: bool = False,
) -> Facture:
    return Facture(
        fournisseur,
        slug,
        adresse,
        numero,
        jour,
        tuple(Ligne(d, q, p) for d, q, p in lignes),
        taux,
        scannee,
    )


CAS: tuple[Cas, ...] = (
    Cas(
        dossier="01-degat-des-eaux-nominal",
        titre="Dégât des eaux nominal",
        eprouve="Le parcours complet sans accroc : formule confort, deux pièces exigées, aucun "
        "indicateur de risque, franchise déduite.",
        reference="KAL-26-8101",
        assure=_assure(1, "Léa", "Moreau", True, "7 allée des Tilleuls", "69007", "Lyon"),
        numero_contrat="H-2021-004871",
        formule="confort",
        souscription=date(2021, 3, 15),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="degat_des_eaux",
        survenance=date(2026, 9, 2),
        declaration=date(2026, 9, 4),
        montant_declare=1650.0,
        description="Canalisation rompue sous l'évier, placard et sol de la cuisine abîmés.",
        circonstances="Dans la soirée, une canalisation a cédé sous l'évier de ma cuisine et "
        "l'eau s'est répandue sur le sol et dans le placard avant que je puisse couper "
        "l'arrivée d'eau. Un plombier est intervenu le lendemain pour remplacer le tronçon "
        "et remettre en état le meuble.",
        factures=(
            _facture(
                "Plomberie Delorme",
                "plomberie-delorme",
                "3 rue des Artisans, 69007 Lyon",
                "2026-118",
                date(2026, 9, 3),
                [
                    ("Recherche de fuite", 1, 150.0),
                    ("Remplacement de la canalisation en cuivre", 1, 850.0),
                    ("Main d'oeuvre (heures)", 5, 60.0),
                    ("Remise en état du placard sous évier", 1, 200.0),
                ],
                0.10,
            ),
        ),
        photo="placard-sous-evier",
        motif_contient=("Remboursement accordé",),
    ),
    Cas(
        dossier="02-plafond-essentiel",
        titre="Plafond de la formule essentiel",
        eprouve="Incendie à 4 400 € sous la formule essentiel : franchise de 300 €, puis plafond "
        "de 3 000 € atteint ; le motif doit le rappeler.",
        reference="KAL-26-8102",
        assure=_assure(2, "Hugo", "Lambert", False, "18 rue des Hirondelles", "44000", "Nantes"),
        numero_contrat="H-2022-006102",
        formule="essentiel",
        souscription=date(2022, 5, 10),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="incendie",
        survenance=date(2026, 8, 25),
        declaration=date(2026, 8, 27),
        montant_declare=4400.0,
        description="Incendie de cuisine d'origine électrique, tableau et câblage détruits.",
        circonstances="Un court-circuit a provoqué un départ de feu dans la cuisine, que les "
        "pompiers ont éteint avant qu'il ne gagne les autres pièces. Le tableau électrique "
        "et le câblage de la cuisine ont été détruits.",
        factures=(
            _facture(
                "Électricité Vasseur & Fils",
                "electricite-vasseur",
                "21 avenue de la Gare, 44000 Nantes",
                "F-2026-0457",
                date(2026, 8, 31),
                [
                    ("Remplacement du tableau électrique", 1, 1800.0),
                    ("Réfection du câblage de la cuisine", 1, 1400.0),
                    ("Main d'oeuvre (heures)", 12, 60.0),
                    ("Évacuation des déchets", 1, 80.0),
                ],
                0.10,
            ),
        ),
        photo="cuisine-incendiee",
        motif_contient=("Plafond de la formule essentiel atteint", "3 000,00 €"),
    ),
    Cas(
        dossier="03-vol-avec-plainte",
        titre="Vol avec dépôt de plainte",
        eprouve="Vol sous la formule confort : facture et dépôt de plainte exigés (et non une "
        "photo), déclaration en 2 jours pour 5 autorisés, aucun indicateur de risque.",
        reference="KAL-26-8103",
        assure=_assure(
            3, "Nadia", "Benali", True, "42 boulevard des Mimosas", "13008", "Marseille"
        ),
        numero_contrat="H-2020-003377",
        formule="confort",
        souscription=date(2020, 11, 2),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="vol",
        survenance=date(2026, 9, 14),
        declaration=date(2026, 9, 16),
        montant_declare=1800.0,
        description="Cambriolage avec effraction, ordinateur portable, écran et imprimante volés.",
        circonstances="En rentrant le soir, j'ai trouvé la porte d'entrée forcée et le bureau "
        "vidé de mon matériel informatique, soit un ordinateur portable, un écran et une "
        "imprimante. J'ai déposé plainte dès le lendemain.",
        factures=(
            _facture(
                "Informatique Pixelis",
                "informatique-pixelis",
                "8 cours Lieutaud, 13006 Marseille",
                "PX-2025-3391",
                date(2025, 11, 20),
                [
                    ("Ordinateur portable 15 pouces", 1, 1100.0),
                    ("Écran 27 pouces", 1, 250.0),
                    ("Imprimante multifonction", 1, 150.0),
                ],
                0.20,
            ),
        ),
        photo="porte-forcee",
        plainte=Plainte("Commissariat central de Marseille 8e", "2026-1423", date(2026, 9, 15)),
        motif_contient=("Remboursement accordé",),
    ),
    Cas(
        dossier="04-fraude-elevee",
        titre="Risque anti-fraude élevé",
        eprouve="Vol de 7 200 € sur un contrat vieux de 82 jours, avec 3 sinistres sur 12 mois : "
        "le partenaire note 0,88 (élevé), escalade vers la cellule anti-fraude.",
        reference="KAL-26-8104",
        assure=_assure(4, "Julien", "Perrot", False, "5 rue des Vignes", "33000", "Bordeaux"),
        numero_contrat="H-2026-009204",
        formule="premium",
        souscription=date(2026, 6, 20),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="vol",
        survenance=date(2026, 9, 10),
        declaration=date(2026, 9, 12),
        montant_declare=7200.0,
        description="Vol avec effraction, téléviseur, consoles, ordinateur et matériel audio.",
        circonstances="À mon retour de week-end, j'ai constaté que la porte-fenêtre avait été "
        "forcée et que le salon avait été vidé de son téléviseur, de sa barre de son, de "
        "deux consoles de jeux et d'un ordinateur. J'ai déposé plainte la veille.",
        sinistres_12_mois=3,
        factures=(
            _facture(
                "Audiovisuel Lacour",
                "audiovisuel-lacour",
                "14 cours de l'Intendance, 33000 Bordeaux",
                "AL-26-1180",
                date(2026, 7, 2),
                [
                    ("Téléviseur OLED 65 pouces", 1, 2500.0),
                    ("Barre de son", 1, 800.0),
                    ("Console de jeux", 2, 450.0),
                    ("Ordinateur de bureau", 1, 1800.0),
                ],
                0.20,
            ),
        ),
        photo="salon-cambriole",
        plainte=Plainte("Commissariat de Bordeaux centre", "2026-3310", date(2026, 9, 11)),
        motif_contient=("Suspicion de fraude",),
    ),
    Cas(
        dossier="05-contrat-resilie",
        titre="Contrat résilié",
        eprouve="Contrat résilié avant le sinistre : refus immédiat (E1), sans consulter le "
        "partenaire.",
        reference="KAL-26-8105",
        assure=_assure(5, "Sophie", "Garnier", True, "27 rue des Peupliers", "59000", "Lille"),
        numero_contrat="H-2019-001845",
        formule="confort",
        souscription=date(2019, 2, 18),
        statut="resilie",
        cotisations_a_jour=True,
        date_resiliation=date(2026, 6, 30),
        type_sinistre="degat_des_eaux",
        survenance=date(2026, 8, 18),
        declaration=date(2026, 8, 20),
        montant_declare=1100.0,
        description="Fuite au plafond de la salle de bain, peinture et plâtre à refaire.",
        circonstances="Une fuite venant de l'étage du dessus a abîmé le plafond de ma salle de "
        "bain : la peinture a cloqué et le plâtre s'est détaché par endroits.",
        factures=(
            _facture(
                "Plomberie Delattre",
                "plomberie-delattre",
                "12 rue Nationale, 59000 Lille",
                "2026-77",
                date(2026, 8, 22),
                [
                    ("Réparation de la fuite", 1, 600.0),
                    ("Main d'oeuvre (heures)", 4, 60.0),
                    ("Peinture et plâtrerie du plafond", 1, 160.0),
                ],
                0.10,
            ),
        ),
        photo="plafond-fuite",
        motif_contient=("contrat non actif",),
    ),
    Cas(
        dossier="06-facture-illisible",
        titre="Facture scannée illisible",
        eprouve="La facture est un PDF scanné, sans texte : pièce illisible, aucun dépôt de "
        "complément, escalade vers un gestionnaire (pièces manquantes).",
        reference="KAL-26-8106",
        assure=_assure(6, "Thomas", "Roux", False, "14 impasse des Cerisiers", "31000", "Toulouse"),
        numero_contrat="H-2023-007730",
        formule="confort",
        souscription=date(2023, 1, 9),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="degat_des_eaux",
        survenance=date(2026, 9, 6),
        declaration=date(2026, 9, 8),
        montant_declare=2200.0,
        description="Ballon d'eau chaude percé, carrelage et plinthes de la buanderie abîmés.",
        circonstances="Le ballon d'eau chaude de la buanderie s'est percé pendant la nuit et "
        "a inondé la pièce, abîmant le carrelage et les plinthes. Mon installateur m'a remis "
        "sa facture sous forme de photocopie scannée.",
        factures=(
            _facture(
                "Chauffage Service Occitan",
                "chauffage-occitan",
                "5 route de Revel, 31400 Toulouse",
                "CSO-2026-0912",
                date(2026, 9, 9),
                [
                    ("Remplacement du ballon d'eau chaude", 1, 1100.0),
                    ("Dépose et évacuation de l'ancien ballon", 1, 150.0),
                    ("Main d'oeuvre (heures)", 8, 60.0),
                    ("Remise en état du carrelage", 1, 270.0),
                ],
                0.10,
                scannee=True,
            ),
        ),
        photo="ballon-eau-chaude",
        motif_contient=("Pièces manquantes", "facture"),
    ),
    Cas(
        dossier="07-seuil-delegation",
        titre="Seuil de délégation dépassé",
        eprouve="Incendie de 12 000 € sous la formule premium (sans franchise) : le montant "
        "dépasse 10 000 €, escalade vers un gestionnaire après un avis de risque faible.",
        reference="KAL-26-8107",
        assure=_assure(7, "Isabelle", "Fournier", True, "9 rue du Moulin", "35000", "Rennes"),
        numero_contrat="H-2018-000912",
        formule="premium",
        souscription=date(2018, 4, 23),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="incendie",
        survenance=date(2026, 8, 30),
        declaration=date(2026, 9, 1),
        montant_declare=12000.0,
        description="Incendie de la cuisine, meubles, électroménager et cloisons détruits.",
        circonstances="Un feu de friteuse a embrasé la cuisine pendant mon absence. La cuisine "
        "équipée, l'électroménager encastré et les cloisons voisines sont détruits.",
        factures=(
            _facture(
                "Cuisines & Rénovation Ouest",
                "cuisines-renovation-ouest",
                "60 boulevard de la Liberté, 35000 Rennes",
                "CRO-26-0210",
                date(2026, 9, 10),
                [
                    ("Cuisine équipée sur mesure", 1, 6500.0),
                    ("Électroménager encastrable", 1, 2000.0),
                    ("Plâtrerie et peinture", 1, 1000.0),
                    ("Main d'oeuvre (heures)", 10, 50.0),
                ],
                0.20,
            ),
        ),
        photo="cuisine-sinistree",
        motif_contient=("Seuil de délégation dépassé",),
    ),
    Cas(
        dossier="08-carence",
        titre="Sinistre pendant la carence",
        eprouve="Sinistre 16 jours après la souscription : la carence de 30 jours s'applique, "
        "refus (E3).",
        reference="KAL-26-8108",
        assure=_assure(8, "Karim", "Haddad", False, "31 rue des Jardiniers", "67000", "Strasbourg"),
        numero_contrat="H-2026-009318",
        formule="confort",
        souscription=date(2026, 8, 20),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="degat_des_eaux",
        survenance=date(2026, 9, 5),
        declaration=date(2026, 9, 7),
        montant_declare=1320.0,
        description="Infiltration par la toiture, plafond de la chambre et isolation abîmés.",
        circonstances="Pendant l'orage, de l'eau s'est infiltrée par la toiture et a traversé "
        "le plafond de la chambre, détériorant la peinture et l'isolation.",
        factures=(
            _facture(
                "Couverture Alsace Toitures",
                "toitures-alsace",
                "2 rue de la Tuilerie, 67000 Strasbourg",
                "CAT-26-318",
                date(2026, 9, 8),
                [
                    ("Réparation de la toiture", 1, 800.0),
                    ("Main d'oeuvre (heures)", 5, 60.0),
                    ("Fournitures", 1, 100.0),
                ],
                0.10,
            ),
        ),
        photo="plafond-chambre",
        motif_contient=("carence",),
    ),
    Cas(
        dossier="09-declaration-hors-delai",
        titre="Vol déclaré hors délai",
        eprouve="Vol déclaré 8 jours après les faits, pour 5 jours autorisés : refus (E4), "
        "alors que toutes les pièces sont fournies.",
        reference="KAL-26-8109",
        assure=_assure(9, "Élodie", "Marchand", True, "6 chemin des Vignes", "21000", "Dijon"),
        numero_contrat="H-2022-005581",
        formule="confort",
        souscription=date(2022, 9, 12),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="vol",
        survenance=date(2026, 8, 20),
        declaration=date(2026, 8, 28),
        montant_declare=1200.0,
        description="Vol d'outillage et de matériel de jardin dans la cave et le garage.",
        circonstances="Des cambrioleurs ont forcé la porte de la cave et emporté l'outillage "
        "électroportatif et la tondeuse. J'ai déposé plainte le 21 août.",
        factures=(
            _facture(
                "Bricolage Dijon Pro",
                "bricolage-dijon-pro",
                "33 avenue Jean-Jaurès, 21000 Dijon",
                "BDP-2024-8820",
                date(2024, 5, 3),
                [
                    ("Outillage électroportatif", 1, 700.0),
                    ("Tondeuse électrique", 1, 300.0),
                ],
                0.20,
            ),
        ),
        photo="cave-forcee",
        plainte=Plainte("Commissariat de Dijon", "2026-2087", date(2026, 8, 21)),
        motif_contient=("déclaration hors délai",),
    ),
    Cas(
        dossier="10-cotisations-impayees",
        titre="Cotisations impayées",
        eprouve="Contrat actif mais cotisations en retard : refus (E2).",
        reference="KAL-26-8110",
        assure=_assure(10, "Marc", "Lefèvre", False, "22 rue des Noyers", "38000", "Grenoble"),
        numero_contrat="H-2020-002764",
        formule="confort",
        souscription=date(2020, 6, 30),
        statut="actif",
        cotisations_a_jour=False,
        type_sinistre="incendie",
        survenance=date(2026, 9, 1),
        declaration=date(2026, 9, 3),
        montant_declare=2750.0,
        description="Départ de feu dans le garage, murs et porte noircis, installation à refaire.",
        circonstances="Un départ de feu s'est produit dans mon garage, probablement à cause "
        "d'un chargeur de batterie. Les murs et la porte sont noircis par les suies.",
        factures=(
            _facture(
                "Rénov'Isère",
                "renov-isere",
                "4 rue des Alpes, 38000 Grenoble",
                "RI-2026-0345",
                date(2026, 9, 5),
                [
                    ("Nettoyage des suies", 1, 900.0),
                    ("Peinture et enduits", 1, 1000.0),
                    ("Main d'oeuvre (heures)", 10, 60.0),
                ],
                0.10,
            ),
        ),
        photo="garage-noirci",
        motif_contient=("cotisations impayées",),
    ),
    Cas(
        dossier="11-risque-modere",
        titre="Risque anti-fraude modéré",
        eprouve="Dégât des eaux de 5 500 € sur un contrat de 60 jours : le partenaire note 0,46 "
        "(modéré), escalade vers un gestionnaire pour contrôle renforcé.",
        reference="KAL-26-8111",
        assure=_assure(11, "Claire", "Dubois", True, "3 rue des Oliviers", "34000", "Montpellier"),
        numero_contrat="H-2026-008870",
        formule="confort",
        souscription=date(2026, 7, 1),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="degat_des_eaux",
        survenance=date(2026, 8, 30),
        declaration=date(2026, 9, 1),
        montant_declare=5500.0,
        description="Inondation du rez-de-chaussée, parquet du salon et des chambres gonflé.",
        circonstances="Une rupture de la nourrice du chauffe-eau a inondé tout le "
        "rez-de-chaussée. Le parquet du salon et des chambres a gonflé et se soulève.",
        factures=(
            _facture(
                "Parquets du Languedoc",
                "parquets-languedoc",
                "19 route de Nîmes, 34000 Montpellier",
                "PL-26-0604",
                date(2026, 9, 12),
                [
                    ("Fourniture de parquet massif (m²)", 30, 90.0),
                    ("Pose du parquet (m²)", 30, 40.0),
                    ("Ponçage et vitrification", 1, 600.0),
                    ("Plinthes", 1, 300.0),
                    ("Traitement de l'humidité", 1, 200.0),
                ],
                0.10,
            ),
        ),
        photo="parquet-gonfle",
        motif_contient=("Contrôle renforcé",),
    ),
    Cas(
        dossier="12-premium-deux-factures",
        titre="Formule premium, deux factures",
        eprouve="Incendie sous la formule premium : deux factures dont la somme (7 700 €) est "
        "remboursée sans franchise ; le montant dépasse 5 000 € donc le partenaire est "
        "consulté (faible).",
        reference="KAL-26-8112",
        assure=_assure(12, "Antoine", "Girard", False, "17 rue des Mimosas", "06000", "Nice"),
        numero_contrat="H-2017-000398",
        formule="premium",
        souscription=date(2017, 10, 5),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="incendie",
        survenance=date(2026, 8, 12),
        declaration=date(2026, 8, 14),
        montant_declare=7700.0,
        description="Incendie du salon, murs, sols et menuiseries à remplacer.",
        circonstances="Un feu s'est déclaré dans le salon à la suite d'un court-circuit. Les "
        "murs, le sol et quatre fenêtres sont à remplacer, et l'ensemble doit être nettoyé "
        "et désodorisé.",
        factures=(
            _facture(
                "Nettoyage Azur Sinistres",
                "nettoyage-azur",
                "52 avenue Borriglione, 06100 Nice",
                "NAS-2026-231",
                date(2026, 8, 20),
                [
                    ("Dépollution et nettoyage des suies", 1, 1800.0),
                    ("Désodorisation", 1, 500.0),
                    ("Évacuation des gravats", 1, 700.0),
                ],
                0.10,
            ),
            _facture(
                "Menuiserie Riviera",
                "menuiserie-riviera",
                "7 rue de la Buffa, 06000 Nice",
                "MR-2026-0098",
                date(2026, 8, 28),
                [
                    ("Fenêtre double vitrage", 4, 700.0),
                    ("Pose des fenêtres", 1, 800.0),
                    ("Porte intérieure", 1, 400.0),
                ],
                0.10,
            ),
        ),
        photo="salon-suie",
        motif_contient=("Remboursement accordé",),
    ),
    Cas(
        dossier="13-bris-de-glace-ecart-declare",
        titre="Bris de glace, déclaré supérieur au justifié",
        eprouve="Montant déclaré (1 100 €) supérieur de plus de 20 % à la facture (880 €) : le "
        "remboursement suit la facture, et l'indicateur F4 déclenche une consultation du "
        "partenaire (faible).",
        reference="KAL-26-8113",
        assure=_assure(13, "Julie", "Mercier", True, "8 rue des Acacias", "37000", "Tours"),
        numero_contrat="H-2021-004015",
        formule="confort",
        souscription=date(2021, 12, 1),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="bris_de_glace",
        survenance=date(2026, 9, 18),
        declaration=date(2026, 9, 19),
        montant_declare=1100.0,
        description="Baie vitrée brisée par une branche pendant l'orage.",
        circonstances="Pendant l'orage de la nuit, une branche est tombée sur la baie vitrée "
        "du salon et l'a brisée.",
        precision_montant="Ce montant comprend, en plus du vitrage, un rideau et du petit "
        "mobilier détériorés.",
        factures=(
            _facture(
                "Vitrerie Touraine",
                "vitrerie-touraine",
                "25 rue Colbert, 37000 Tours",
                "VT-26-0507",
                date(2026, 9, 21),
                [
                    ("Vitrage feuilleté sur mesure", 1, 650.0),
                    ("Pose et calfeutrement", 1, 100.0),
                    ("Évacuation de l'ancien vitrage", 1, 50.0),
                ],
                0.10,
            ),
        ),
        photo="baie-vitree-brisee",
        motif_contient=("Remboursement accordé",),
    ),
    Cas(
        dossier="14-piece-manquante",
        titre="Pièce exigée absente",
        eprouve="Dégât des eaux sans aucune photo : la pièce exigée manque et l'assuré n'a rien "
        "déposé, escalade vers un gestionnaire.",
        reference="KAL-26-8114",
        assure=_assure(14, "Paul", "Vidal", False, "12 rue des Tanneurs", "76000", "Rouen"),
        numero_contrat="H-2021-004492",
        formule="confort",
        souscription=date(2021, 3, 22),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="degat_des_eaux",
        survenance=date(2026, 9, 9),
        declaration=date(2026, 9, 10),
        montant_declare=1540.0,
        description="Fuite du lave-linge, sol de la salle de bain et meuble vasque gonflés.",
        circonstances="Le tuyau d'alimentation de mon lave-linge s'est rompu pendant un cycle. "
        "Le sol de la salle de bain et le meuble vasque ont gonflé.",
        factures=(
            _facture(
                "Dépannage Rouen Plomberie",
                "depannage-rouen",
                "30 rue Jeanne-d'Arc, 76000 Rouen",
                "DRP-2026-415",
                date(2026, 9, 10),
                [
                    ("Remplacement du tuyau d'alimentation", 1, 300.0),
                    ("Remplacement du meuble vasque", 1, 700.0),
                    ("Main d'oeuvre (heures)", 6, 60.0),
                    ("Revêtement de sol", 1, 40.0),
                ],
                0.10,
            ),
        ),
        photo=None,
        motif_contient=("Pièces manquantes", "photo"),
    ),
    Cas(
        dossier="15-garantie-non-couverte",
        titre="Garantie non couverte par la formule",
        eprouve="Vol sous la formule essentiel, qui ne couvre ni les vols ni les bris de glace : "
        "refus (E5), pièces complètes par ailleurs.",
        reference="KAL-26-8115",
        assure=_assure(15, "Sarah", "Cohen", True, "4 rue des Roses", "57000", "Metz"),
        numero_contrat="H-2022-006240",
        formule="essentiel",
        souscription=date(2022, 2, 14),
        statut="actif",
        cotisations_a_jour=True,
        type_sinistre="vol",
        survenance=date(2026, 9, 11),
        declaration=date(2026, 9, 12),
        montant_declare=1440.0,
        description="Cambriolage par la fenêtre, appareil photo et objectif volés.",
        circonstances="Un cambrioleur est entré par la fenêtre de la chambre, restée fermée "
        "mais forcée, et a emporté mon appareil photo et son objectif.",
        factures=(
            _facture(
                "Optique et Image Lorraine",
                "image-lorraine",
                "16 rue Serpenoise, 57000 Metz",
                "OIL-2025-1147",
                date(2025, 12, 6),
                [
                    ("Appareil photo hybride", 1, 900.0),
                    ("Objectif 24-70 mm", 1, 300.0),
                ],
                0.20,
            ),
        ),
        photo="fenetre-forcee",
        plainte=Plainte("Commissariat de Metz", "2026-1198", date(2026, 9, 11)),
        motif_contient=("non couvert par la formule essentiel",),
    ),
)


# ---------------------------------------------------------------------------------- formats


def montant(valeur: float) -> str:
    """1650 -> « 1 650,00 »."""
    return f"{valeur:,.2f}".replace(",", " ").replace(".", ",")


def date_longue(jour: date) -> str:
    return f"{'1er' if jour.day == 1 else jour.day} {MOIS[jour.month - 1]} {jour.year}"


def date_etiquetee(jour: date, indice: int) -> str:
    """Trois écritures de date, en alternance d'un cas à l'autre : 02/09/2026, 2026-09-02, 2 sept."""
    return (f"{jour:%d/%m/%Y}", jour.isoformat(), date_longue(jour))[indice % 3]


def fichiers(cas: Cas) -> list[tuple[str, str]]:
    """Fichiers du dossier dans l'ordre de dépôt : (nom, rôle de la console)."""
    noms = [("contrat.pdf", "contrat"), ("declaration-sinistre.pdf", "declaration")]
    noms += [(f"facture-{f.slug}.pdf", "facture") for f in cas.factures]
    if cas.photo:
        noms.append((f"photo-{cas.photo}.png", "photo"))
    if cas.plainte:
        noms.append(("depot-de-plainte.pdf", "plainte"))
    return [(f"{i}-{nom}", role) for i, (nom, role) in enumerate(noms, start=1)]


# ------------------------------------------------------------------------- PDF « étiquetés »


def _pdf_lignes(chemin: Path, titre: str, lignes: list[tuple[str, str]]) -> None:
    """PDF de lignes simples, au style de scripts/exemple_dossier_pdf.py ; ne retourne pas à la ligne."""
    pdf = canvas.Canvas(str(chemin), pagesize=A4, invariant=1)
    pdf.setTitle(titre)
    pdf.setAuthor(AUTEUR)
    y = 800
    for genre, texte in lignes:
        police, taille = {
            "titre": ("Helvetica-Bold", 15),
            "sous": ("Helvetica-Oblique", 9),
        }.get(genre, ("Helvetica", 11))
        largeur = stringWidth(texte, police, taille)
        if largeur > A4[0] - 2 * MARGE:
            raise ValueError(f"ligne trop longue pour la page ({largeur:.0f} pt) : {texte}")
        y -= {"titre": 24, "sous": 22}.get(genre, 17)
        pdf.setFont(police, taille)
        pdf.drawString(MARGE, y, texte)
    pdf.save()


def contrat_etiquete(cas: Cas, indice: int) -> list[tuple[str, str]]:
    a = cas.assure
    statut = {"actif": "actif", "suspendu": "suspendu", "resilie": "résilié"}[cas.statut]
    lignes = [
        ("titre", "Contrat d'assurance habitation"),
        ("sous", "Document fictif, généré pour essayer Kaldera V2"),
        ("champ", f"Numéro client : {a.id_client}"),
        ("champ", f"Nom : {a.nom}"),
        ("champ", f"Prénom : {a.prenom}"),
        ("champ", f"E-mail : {a.email}"),
        ("champ", f"Téléphone : {a.telephone}"),
        ("champ", f"IBAN : {a.iban}"),
        ("champ", f"Adresse : {a.adresse}"),
        ("champ", f"Code postal : {a.code_postal}"),
        ("champ", f"Numéro de contrat : {cas.numero_contrat}"),
        ("champ", f"Formule : {cas.formule}"),
        ("champ", f"Date de souscription : {date_etiquetee(cas.souscription, indice)}"),
        ("champ", f"Statut du contrat : {statut}"),
        ("champ", f"Cotisations à jour : {'oui' if cas.cotisations_a_jour else 'non'}"),
    ]
    return lignes


def declaration_etiquetee(cas: Cas, indice: int) -> list[tuple[str, str]]:
    return [
        ("titre", "Déclaration de sinistre"),
        ("sous", "Document fictif, généré pour essayer Kaldera V2"),
        ("champ", f"Référence : {cas.reference}"),
        ("champ", f"Type de sinistre : {TYPES[cas.type_sinistre][0]}"),
        ("champ", f"Date de survenance : {date_etiquetee(cas.survenance, indice)}"),
        ("champ", f"Date de déclaration : {date_etiquetee(cas.declaration, indice)}"),
        ("champ", f"Montant déclaré : {montant(cas.montant_declare)} €"),
        ("champ", f"Description : {cas.description}"),
        ("champ", f"Sinistres sur 12 mois : {cas.sinistres_12_mois}"),
    ]


def facture_etiquetee(f: Facture) -> list[tuple[str, str]]:
    lignes = [
        ("titre", f"Facture n° {f.numero} — {f.fournisseur}"),
        ("sous", "Document fictif, généré pour essayer Kaldera V2"),
        ("champ", f"Date de facture : {f.date:%d/%m/%Y}"),
    ]
    lignes += [
        ("champ", f"{ligne.designation} : {montant(ligne.total_ht)} €") for ligne in f.lignes
    ]
    lignes += [
        ("champ", f"Total HT : {montant(f.total_ht)} €"),
        ("champ", f"TVA {f.taux_tva * 100:.0f} % : {montant(f.tva)} €"),
        ("champ", f"Total TTC : {montant(f.total_ttc)} €"),
    ]
    return lignes


def plainte_etiquetee(cas: Cas, p: Plainte) -> list[tuple[str, str]]:
    a = cas.assure
    return [
        ("titre", "Récépissé de dépôt de plainte"),
        ("sous", "Document fictif, généré pour essayer Kaldera V2"),
        ("champ", p.commissariat),
        ("champ", f"Numéro de plainte : {p.numero}"),
        ("champ", f"Date du dépôt : {p.date:%d/%m/%Y}"),
        ("champ", f"Plaignant : {a.prenom} {a.nom}"),
        ("champ", f"Lieu des faits : {a.adresse}"),
        ("champ", f"Date des faits : {cas.survenance:%d/%m/%Y}"),
        ("champ", "Nature des faits : vol avec effraction"),
    ]


# ----------------------------------------------------------------------- PDF en texte libre

STYLE_TITRE = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=15, leading=20)
STYLE_TEXTE = ParagraphStyle("texte", fontName="Helvetica", fontSize=11, leading=15, spaceAfter=9)
STYLE_DROITE = ParagraphStyle("droite", parent=STYLE_TEXTE, alignment=2)
STYLE_GRAS = ParagraphStyle("gras", parent=STYLE_TEXTE, fontName="Helvetica-Bold")


def _pdf_libre(chemin: Path, titre: str, elements: list[Any]) -> None:
    document = SimpleDocTemplate(
        str(chemin),
        pagesize=A4,
        leftMargin=MARGE,
        rightMargin=MARGE,
        topMargin=MARGE,
        bottomMargin=MARGE,
        title=titre,
        author=AUTEUR,
        invariant=1,
    )
    document.build(elements)


def _p(texte: str, style: ParagraphStyle = STYLE_TEXTE) -> Paragraph:
    return Paragraph(escape(texte), style)


def contrat_libre(cas: Cas) -> list[Any]:
    a = cas.assure
    franchise, plafond, garanties = FORMULES[cas.formule]
    sans_franchise = "sans franchise" if franchise == 0 else f"une franchise de {franchise} euros"
    if cas.statut == "resilie" and cas.date_resiliation:
        statut = (
            "Ce contrat a fait l'objet d'une résiliation à l'initiative de l'assureur, effective "
            f"depuis le {date_longue(cas.date_resiliation)} : il n'est donc plus en vigueur."
        )
    else:
        statut = "À la date d'édition de ces conditions particulières, le contrat est en vigueur."
    cotisations = (
        "Les cotisations sont à jour et aucune échéance n'est en attente de règlement."
        if cas.cotisations_a_jour
        else "Les deux dernières échéances de cotisation restent impayées à ce jour."
    )
    return [
        _p("Conditions particulières — assurance habitation", STYLE_TITRE),
        Spacer(1, 14),
        _p(
            f"{a.civilite} {a.prenom} {a.nom}, client numéro {a.id_client}, demeurant "
            f"{a.adresse}, est assuré{a.e} auprès de Kaldera Assurances, compagnie fictive, au "
            f"titre du contrat d'assurance habitation numéro {cas.numero_contrat}."
        ),
        _p(
            f"Ce contrat a été souscrit le {date_longue(cas.souscription)}. L'assuré{a.e} a "
            f"choisi la formule {cas.formule.capitalize()}, {garanties}, avec {sans_franchise} "
            f"et un plafond de {montant(plafond)[:-3]} euros par sinistre."
        ),
        _p(f"{statut} {cotisations}"),
        _p(
            f"Pour toute correspondance, {a.civilite.lower()} {a.nom} peut être joint{a.e} par "
            f"courriel à l'adresse {a.email} ou par téléphone au {a.telephone}. Les "
            f"remboursements éventuels seront versés sur le compte bancaire dont l'IBAN "
            f"d'exemple est {a.iban}."
        ),
        _p("Document fictif, généré pour essayer Kaldera V2."),
    ]


def declaration_libre(cas: Cas) -> list[Any]:
    a = cas.assure
    historique = (
        "Je n'ai déclaré aucun autre sinistre au cours des douze derniers mois."
        if cas.sinistres_12_mois == 0
        else f"Pour information, j'ai déjà déclaré {NOMBRES[cas.sinistres_12_mois]} sinistres "
        "au cours des douze derniers mois."
    )
    return [
        _p(f"{a.ville}, le {date_longue(cas.declaration)}", STYLE_DROITE),
        _p(f"{a.prenom} {a.nom}"),
        _p(a.adresse),
        Spacer(1, 10),
        _p(f"Objet — déclaration de sinistre, dossier {cas.reference}", STYLE_GRAS),
        _p("Madame, Monsieur,"),
        _p(
            f"Je vous écris pour vous déclarer {TYPES[cas.type_sinistre][1]} survenu le "
            f"{date_longue(cas.survenance)} à mon domicile, {a.adresse}. {cas.circonstances}"
        ),
        _p(
            f"J'évalue le montant total de mes dommages à {montant(cas.montant_declare)} euros. "
            f"{cas.precision_montant} {historique}".replace("  ", " ")
        ),
        _p(
            "Les justificatifs seront déposés dans mon espace en ligne. Je reste à votre "
            "disposition pour tout renseignement complémentaire."
        ),
        _p("Cordialement,"),
        _p(f"{a.prenom} {a.nom}"),
    ]


def facture_libre(f: Facture, cas: Cas) -> list[Any]:
    """Facture réaliste : lignes de prestation, TVA, total. Le total garde un « : » (voir README)."""
    a = cas.assure
    lignes = [["Désignation", "Qté", "PU HT", "Total HT"]]
    lignes += [
        [ligne.designation, str(ligne.quantite), f"{montant(ligne.prix_ht)} €"]
        + [f"{montant(ligne.total_ht)} €"]
        for ligne in f.lignes
    ]
    tableau = Table(lignes, colWidths=[255, 40, 90, 90], repeatRows=1)
    tableau.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    totaux = Table(
        [
            ["Total HT", f"{montant(f.total_ht)} €"],
            [f"TVA à {f.taux_tva * 100:.0f} %", f"{montant(f.tva)} €"],
        ],
        colWidths=[385, 90],
    )
    totaux.setStyle(
        TableStyle(
            [("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("ALIGN", (1, 0), (1, -1), "RIGHT")]
        )
    )
    return [
        _p(f.fournisseur, STYLE_TITRE),
        _p(f"{f.adresse}. SIRET fictif 000 000 000 00000."),
        Spacer(1, 8),
        _p(f"Facture n° {f.numero} du {date_longue(f.date)}", STYLE_GRAS),
        _p(f"Facturé à {a.civilite} {a.prenom} {a.nom}, {a.adresse}."),
        _p(
            "Travaux et fournitures réalisés à l'adresse ci-dessus suite au sinistre "
            f"du {date_longue(cas.survenance)}."
        ),
        Spacer(1, 6),
        tableau,
        Spacer(1, 6),
        totaux,
        Spacer(1, 4),
        _p(f"Total TTC : {montant(f.total_ttc)} €", STYLE_GRAS),
        _p("Règlement à réception par virement. Document fictif, généré pour essayer Kaldera V2."),
    ]


def plainte_libre(cas: Cas, p: Plainte) -> list[Any]:
    a = cas.assure
    return [
        _p(f"Procès-verbal de dépôt de plainte numéro {p.numero}", STYLE_TITRE),
        Spacer(1, 12),
        _p(
            f"Le {date_longue(p.date)}, {a.civilite} {a.prenom} {a.nom}, demeurant {a.adresse}, "
            f"s'est présenté{a.e} au {p.commissariat} pour déposer plainte contre X."
        ),
        _p(
            f"{a.civilite} {a.nom} déclare que son domicile a été cambriolé avec effraction le "
            f"{date_longue(cas.survenance)} et que plusieurs biens lui ont été dérobés. La "
            "plainte a été enregistrée et un récépissé a été remis au déclarant."
        ),
        _p("Document fictif, généré pour essayer Kaldera V2."),
    ]


# ---------------------------------------------------------------------------- facture scannée


def facture_scannee(f: Facture, cas: Cas, chemin: Path) -> None:
    """PDF composé d'une seule image : aucune couche de texte, donc rien à extraire."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    largeur, hauteur = 700, 990
    image = Image.new("L", (largeur, hauteur), 236)
    dessin = ImageDraw.Draw(image)
    try:
        police = ImageFont.load_default(size=19)
    except TypeError:  # Pillow trop ancien : police bitmap, plus petite mais lisible
        police = ImageFont.load_default()
    textes = [
        f.fournisseur,
        f.adresse,
        "",
        f"Facture n° {f.numero} du {f.date:%d/%m/%Y}",
        f"{cas.assure.prenom} {cas.assure.nom}",
        "",
    ]
    textes += [
        f"{ligne.designation}   {ligne.quantite} x {montant(ligne.prix_ht)}   "
        f"{montant(ligne.total_ht)}"
        for ligne in f.lignes
    ]
    textes += [
        "",
        f"Total HT {montant(f.total_ht)} EUR",
        f"TVA {f.taux_tva * 100:.0f} % {montant(f.tva)} EUR",
        f"Total TTC {montant(f.total_ttc)} EUR",
    ]
    y = 70
    for texte in textes:
        # La police intégrée de Pillow n'a pas les lettres accentuées : on les écrit sans accent.
        sans_accent = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
        dessin.text((50, y), sans_accent, fill=40, font=police)
        y += 32
    image = image.rotate(1.3, resample=Image.Resampling.BICUBIC, fillcolor=236)
    graine = random.Random(cas.reference)
    dessin = ImageDraw.Draw(image)
    for _ in range(900):
        x, y = graine.randrange(largeur), graine.randrange(hauteur)
        dessin.point((x, y), fill=graine.randrange(120, 200))
    image = image.filter(ImageFilter.GaussianBlur(0.9))
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", quality=55)
    tampon.seek(0)
    pdf = canvas.Canvas(str(chemin), pagesize=A4, invariant=1)
    pdf.setTitle("Facture scannée")
    pdf.setAuthor(AUTEUR)
    pdf.drawImage(ImageReader(tampon), 0, 0, width=A4[0], height=A4[1])
    pdf.save()


# ------------------------------------------------------------------------------------ photo


def photo(objet: str, style: str, chemin: Path, graine: str) -> None:
    """Image fictive (PNG de plus de 1 Ko) qui évoque le dommage ; déterministe."""
    from PIL import Image, ImageDraw, ImageFont

    largeur, hauteur = 560, 380
    hasard = random.Random(graine)
    haut, bas = {
        "eau": ((226, 221, 206), (196, 190, 174)),
        "feu": ((92, 78, 70), (30, 26, 26)),
        "effraction": ((170, 176, 168), (128, 134, 128)),
        "verre": ((150, 190, 222), (206, 226, 240)),
    }[style]
    image = Image.new("RGB", (largeur, hauteur))
    dessin = ImageDraw.Draw(image)
    for y in range(hauteur):
        t = y / (hauteur - 1)
        dessin.line(
            [(0, y), (largeur, y)], fill=tuple(int(h + (b - h) * t) for h, b in zip(haut, bas))
        )
    if style == "eau":
        for _ in range(7):
            cx, cy = hasard.randrange(80, 480), hasard.randrange(30, 170)
            rx, ry = hasard.randrange(30, 90), hasard.randrange(18, 50)
            for k, couleur in enumerate([(170, 140, 90), (140, 110, 62), (112, 86, 48)]):
                dessin.ellipse(
                    [cx - rx + 9 * k, cy - ry + 6 * k, cx + rx - 9 * k, cy + ry - 6 * k],
                    fill=couleur,
                )
        for x in range(60, 520, 55):
            dessin.line(
                [(x, 190), (x + hasard.randrange(-6, 6), 300)], fill=(110, 135, 170), width=3
            )
        dessin.rectangle([0, 300, largeur, hauteur], fill=(116, 134, 150))
    elif style == "feu":
        for _ in range(9):
            cx, cy = hasard.randrange(40, 520), hasard.randrange(40, 250)
            dessin.ellipse([cx - 60, cy - 40, cx + 60, cy + 40], fill=(14, 13, 13))
        for cx in (120, 250, 400):
            dessin.ellipse([cx - 40, 300, cx + 40, 400], fill=(204, 92, 22))
            dessin.ellipse([cx - 20, 330, cx + 20, 400], fill=(244, 170, 40))
    elif style == "effraction":
        dessin.rectangle([150, 20, 410, hauteur], fill=(112, 76, 46))
        for y0, y1 in ((45, 170), (200, 350)):
            dessin.rectangle([175, y0, 385, y1], outline=(78, 52, 30), width=4)
        dessin.rectangle([360, 185, 395, 235], fill=(170, 170, 170))
        dessin.polygon([(352, 190), (400, 185), (388, 240), (350, 232)], fill=(30, 22, 16))
        for _ in range(8):
            x = hasard.randrange(340, 400)
            dessin.line([(x, 180), (x + hasard.randrange(-14, 14), 245)], fill=(205, 170, 120))
        dessin.line([(430, 120), (365, 215)], fill=(60, 60, 64), width=7)
    else:
        dessin.rectangle([60, 25, 500, 355], fill=(236, 236, 232))
        dessin.rectangle([85, 50, 475, 330], fill=(160, 200, 228))
        dessin.line([(280, 50), (280, 330)], fill=(236, 236, 232), width=8)
        centre = (330, 190)
        for _ in range(14):
            fin = (hasard.randrange(90, 470), hasard.randrange(55, 325))
            dessin.line([centre, fin], fill=(250, 250, 252), width=2)
        dessin.ellipse(
            [centre[0] - 12, centre[1] - 12, centre[0] + 12, centre[1] + 12], fill=(60, 80, 100)
        )
    try:
        police = ImageFont.load_default(size=13)
    except TypeError:
        police = ImageFont.load_default()
    dessin.rectangle([0, hauteur - 24, largeur, hauteur], fill=(20, 20, 20))
    dessin.text(
        (8, hauteur - 20),
        f"Photo fictive - {objet.replace('-', ' ')}",
        fill=(255, 255, 255),
        font=police,
    )
    image.save(chemin, format="PNG")
    if chemin.stat().st_size <= 1024:
        raise ValueError(f"photo trop petite : {chemin}")


# ------------------------------------------------------------------------------ génération


def ecrire_cas(cas: Cas, indice: int, racine: Path) -> None:
    for variante in VARIANTES:
        dossier = racine / cas.dossier / variante
        dossier.mkdir(parents=True, exist_ok=True)
        libre = variante == "B-libre"
        factures = iter(cas.factures)
        for nom, role in fichiers(cas):
            chemin = dossier / nom
            if role == "contrat":
                if libre:
                    _pdf_libre(chemin, "Conditions particulières", contrat_libre(cas))
                else:
                    _pdf_lignes(chemin, "Contrat", contrat_etiquete(cas, indice))
            elif role == "declaration":
                if libre:
                    _pdf_libre(chemin, "Courrier de déclaration", declaration_libre(cas))
                else:
                    _pdf_lignes(chemin, "Déclaration", declaration_etiquetee(cas, indice))
            elif role == "facture":
                f = next(factures)
                if f.scannee:
                    facture_scannee(f, cas, chemin)
                elif libre:
                    _pdf_libre(chemin, f"Facture {f.numero}", facture_libre(f, cas))
                else:
                    _pdf_lignes(chemin, f"Facture {f.numero}", facture_etiquetee(f))
            elif role == "photo":
                assert cas.photo
                photo(cas.photo, TYPES[cas.type_sinistre][2], chemin, cas.reference)
            elif role == "plainte":
                assert cas.plainte
                if libre:
                    _pdf_libre(chemin, "Dépôt de plainte", plainte_libre(cas, cas.plainte))
                else:
                    _pdf_lignes(chemin, "Dépôt de plainte", plainte_etiquetee(cas, cas.plainte))


def generer(racine: Path = RACINE) -> None:
    references = [cas.reference for cas in CAS]
    if len(set(references)) != len(references):
        raise ValueError("références de dossier en double")
    for indice, cas in enumerate(CAS):
        ecrire_cas(cas, indice, racine)


# ---------------------------------------------------------------------------- résultats réels


def documents(dossier: Path) -> list[Any]:
    """Documents d'un dossier de cas, dans l'ordre de dépôt, avec leur rôle de console."""
    from kaldera.extraction import Document

    roles = (
        ("contrat", "contrat"),
        ("declaration-sinistre", "declaration"),
        ("facture-", "facture"),
        ("photo-", "photo"),
        ("depot-de-plainte", "plainte"),
    )
    resultat = []
    for chemin in sorted(dossier.iterdir(), key=lambda c: int(c.name.split("-", 1)[0])):
        reste = chemin.name.split("-", 1)[1]
        role = next(r for debut, r in roles if reste.startswith(debut))
        resultat.append(Document(role, chemin.name, chemin.read_bytes()))
    return resultat


def etablir_attendu(racine: Path = RACINE) -> dict[str, Any]:
    """Extrait la variante A de chaque cas et la fait traiter par le vrai pipeline."""
    import kaldera
    from kaldera import extraction

    attendu: dict[str, Any] = {}
    for cas in CAS:
        analyse = extraction.analyser_documents(
            documents(racine / cas.dossier / "A-etiquete"), [extraction.ExtracteurChamps()]
        )
        if not analyse.pret or analyse.demande["reference"] != cas.reference:
            raise SystemExit(f"{cas.dossier} : analyse non prête ({analyse.manquants})")
        fiche = kaldera.traiter_demande(analyse.demande)
        if fiche["mode_degrade"] or fiche["arret"]:
            raise SystemExit(f"{cas.dossier} : partenaire injoignable ou traitement interrompu")
        manquants = [m for m in cas.motif_contient if m not in fiche["motif"]]
        if manquants:
            raise SystemExit(f"{cas.dossier} : le motif « {fiche['motif']} » ignore {manquants}")
        avis = fiche["avis_fraude"]
        attendu[cas.dossier] = {
            "reference": cas.reference,
            "issue": fiche["issue"],
            "decision": fiche["decision"],
            "montant_rembourse": fiche["montant_rembourse"],
            "file": fiche["file"],
            "mode_degrade": fiche["mode_degrade"],
            "avis_fraude": avis["niveau"] if avis else None,
            "score_fraude": avis["score"] if avis else None,
            "motif_contient": list(cas.motif_contient),
            "fichiers_scannes": [
                nom
                for (nom, role), f in zip(
                    [x for x in fichiers(cas) if x[1] == "facture"], cas.factures, strict=True
                )
                if f.scannee
            ],
        }
    return attendu


def tableau(racine: Path = RACINE) -> str:
    """Tableau récapitulatif (Markdown) : cas, ce qu'il éprouve, résultat attendu."""
    attendu = json.loads((racine / "attendu.json").read_text(encoding="utf-8"))
    lignes = ["| Cas | Ce qu'il éprouve | Résultat attendu |", "|---|---|---|"]
    for cas in CAS:
        a = attendu[cas.dossier]
        if a["issue"] == "escalade":
            resultat = f"escalade `{a['file']}`"
        elif a["decision"] == "acceptee":
            resultat = f"acceptée, {montant(a['montant_rembourse'])} €"
        else:
            resultat = "refusée, 0 €"
        if a["avis_fraude"]:
            resultat += f" (avis anti-fraude {a['avis_fraude']}, {a['score_fraude']:.2f})"
        lignes.append(f"| `{cas.dossier}` ({cas.reference}) | {cas.eprouve} | {resultat} |")
    return "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère les dossiers de cas de exemples/cas/.")
    parser.add_argument("--sortie", type=Path, default=RACINE, help="dossier racine à écrire")
    parser.add_argument(
        "--attendu", action="store_true", help="rejoue le vrai pipeline et écrit attendu.json"
    )
    parser.add_argument("--tableau", action="store_true", help="affiche le tableau récapitulatif")
    args = parser.parse_args()
    if args.tableau:
        print(tableau(args.sortie))
        return
    generer(args.sortie)
    print(f"{len(CAS)} cas écrits dans {args.sortie}")
    if args.attendu:
        attendu = etablir_attendu(args.sortie)
        (args.sortie / "attendu.json").write_text(
            json.dumps(attendu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Résultats attendus établis avec le vrai pipeline : {args.sortie / 'attendu.json'}")


if __name__ == "__main__":
    main()
