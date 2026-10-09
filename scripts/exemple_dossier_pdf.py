"""Génère un dossier PDF d'exemple, aux données fictives, pour essayer l'analyse de dossier.

    uv run python scripts/exemple_dossier_pdf.py [sortie.pdf]

Le dossier suit le format « Libellé : valeur » lu par l'extracteur par champs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

LIGNES = [
    ("titre", "Dossier de demande de remboursement"),
    ("sous", "Document fictif, généré pour essayer Kaldera V2"),
    ("blanc", ""),
    ("section", "Dossier"),
    ("champ", "Référence : KAL-26-7001"),
    ("champ", "Numéro client : C-48210"),
    ("section", "Assuré"),
    ("champ", "Nom : Durand"),
    ("champ", "Prénom : Camille"),
    ("champ", "E-mail : camille.durand@example.org"),
    ("champ", "Téléphone : 06 12 34 56 78"),
    ("champ", "IBAN : FR76 3000 6000 0112 3456 7890 189"),
    ("champ", "Adresse : 12 rue des Lilas, 69003 Lyon"),
    ("champ", "Code postal : 69003"),
    ("section", "Contrat"),
    ("champ", "Numéro de contrat : H-2021-004871"),
    ("champ", "Formule : confort"),
    ("champ", "Date de souscription : 15/03/2021"),
    ("champ", "Statut du contrat : actif"),
    ("champ", "Cotisations à jour : oui"),
    ("section", "Sinistre"),
    ("champ", "Type de sinistre : dégât des eaux"),
    ("champ", "Date de survenance : 02/09/2026"),
    ("champ", "Date de déclaration : 04/09/2026"),
    ("champ", "Montant déclaré : 2 450,00 €"),
    ("champ", "Description : Rupture d'une canalisation sous l'évier, parquet du salon endommagé."),
    ("champ", "Sinistres sur 12 mois : 0"),
    ("section", "Pièces jointes"),
    ("champ", "- Facture plombier : 1 450,00 €"),
    ("champ", "- Facture parquet : 1 000,00 €"),
    ("champ", "- Photo des dégâts"),
]


def generer(chemin: Path) -> None:
    pdf = canvas.Canvas(str(chemin), pagesize=A4)
    pdf.setTitle("Dossier de demande de remboursement (exemple)")
    y = 800
    for genre, texte in LIGNES:
        taille, police = {
            "titre": (16, "Helvetica-Bold"),
            "section": (12, "Helvetica-Bold"),
            "sous": (9, "Helvetica-Oblique"),
        }.get(genre, (11, "Helvetica"))
        y -= {"section": 26, "titre": 22, "blanc": 10}.get(genre, 17)
        pdf.setFont(police, taille)
        pdf.drawString(56, y, texte)
    pdf.save()


PIECES = {
    "contrat.pdf": [
        "Contrat d'assurance habitation",
        "Numéro client : C-48210",
        "Nom : Durand",
        "Prénom : Camille",
        "E-mail : camille.durand@example.org",
        "Téléphone : 06 12 34 56 78",
        "IBAN : FR76 3000 6000 0112 3456 7890 189",
        "Adresse : 12 rue des Lilas, 69003 Lyon",
        "Code postal : 69003",
        "Numéro de contrat : H-2021-004871",
        "Formule : confort",
        "Date de souscription : 15/03/2021",
        "Statut du contrat : actif",
        "Cotisations à jour : oui",
    ],
    "declaration-sinistre.pdf": [
        "Déclaration de sinistre",
        "Référence : KAL-26-7001",
        "Type de sinistre : dégât des eaux",
        "Date de survenance : 02/09/2026",
        "Date de déclaration : 04/09/2026",
        "Montant déclaré : 2 450,00 €",
        "Description : Rupture d'une canalisation sous l'évier, parquet du salon endommagé.",
        "Sinistres sur 12 mois : 0",
    ],
    "facture-plombier.pdf": [
        "Facture n° 2026-118 — Plomberie Martin",
        "Intervention d'urgence : 1 200,00 €",
        "Total TTC : 1 450,00 €",
    ],
    "facture-parquet.pdf": [
        "Facture n° 889 — Parquets du Rhône",
        "Remplacement du parquet",
        "Total TTC : 1 000,00 €",
    ],
}


def generer_pieces(dossier: Path) -> None:
    """Un fichier par pièce demandée (contrat, déclaration, factures) et une photo."""
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, lignes in PIECES.items():
        pdf = canvas.Canvas(str(dossier / nom), pagesize=A4)
        y = 800
        for ligne in lignes:
            pdf.drawString(56, y, ligne)
            y -= 18
        pdf.save()
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (640, 420), (120, 140, 160))
    ImageDraw.Draw(image).text((20, 20), "Photo des degats (exemple)", fill=(255, 255, 255))
    image.save(dossier / "photo-degats.png")


if __name__ == "__main__":
    if "--pieces" in sys.argv:
        generer_pieces(Path("exemples/pieces"))
        print("Pièces d'exemple écrites dans exemples/pieces")
        raise SystemExit(0)
    cible = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("exemples/dossier-exemple.pdf")
    cible.parent.mkdir(parents=True, exist_ok=True)
    generer(cible)
    print(f"Dossier d'exemple écrit : {cible}")
