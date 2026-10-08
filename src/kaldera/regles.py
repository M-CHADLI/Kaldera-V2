"""Référentiel métier : formules, pièces exigées, seuils (docs/specs_metier.md)."""

from __future__ import annotations

from datetime import date

FORMULES: dict[str, dict] = {
    "essentiel": {
        "garanties": {"degat_des_eaux", "incendie"},
        "franchise": 300.0,
        "plafond": 3_000.0,
    },
    "confort": {
        "garanties": {"degat_des_eaux", "incendie", "bris_de_glace", "vol"},
        "franchise": 150.0,
        "plafond": 8_000.0,
    },
    "premium": {
        "garanties": {"degat_des_eaux", "incendie", "bris_de_glace", "vol"},
        "franchise": 0.0,
        "plafond": 20_000.0,
    },
}

PIECES_EXIGEES: dict[str, tuple[str, ...]] = {
    "degat_des_eaux": ("facture", "photo"),
    "incendie": ("facture", "photo"),
    "bris_de_glace": ("facture", "photo"),
    "vol": ("facture", "depot_plainte"),
}

CARENCE_JOURS = 30
DELAI_DECLARATION_JOURS = 30
DELAI_DECLARATION_VOL_JOURS = 5

SEUIL_DELEGATION = 10_000.0

# Mode dégradé (§9) : au-delà, escalade vers la cellule anti-fraude
SEUIL_MODE_DEGRADE = 1_500.0

# Indicateurs déclenchant le contrôle anti-fraude
SEUIL_MONTANT_FRAUDE = 5_000.0
ANCIENNETE_SENSIBLE_JOURS = 90
FREQUENCE_SENSIBLE = 3
ECART_DECLARATION_MAX = 0.20


def jours_entre(debut: str, fin: str) -> int:
    return (date.fromisoformat(fin) - date.fromisoformat(debut)).days
