"""État partagé d'une demande : centralisé, un seul écrivain, auteur de chaque section tracé."""

from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any

# Section métier → seul agent autorisé à en être l'auteur (docs/interface.md, « Trace »).
AUTEURS: dict[str, str] = {
    "eligibilite": "eligibilite",
    "pieces": "pieces",
    "estimation": "estimation",
    "avis_fraude": "antifraude",
    "issue": "superviseur",
}

# Seule la section des pièces connaît plusieurs versions, une par complément.
SECTIONS_VERSIONNEES = {"pieces"}


class ViolationFrontiere(Exception):
    """Un agent a tenté d'écrire une section qui n'est pas la sienne."""


class Etat:
    """État de travail d'une demande, écrit uniquement par le superviseur."""

    def __init__(self, demande: dict[str, Any]) -> None:
        self._demande = deepcopy(demande)
        self._sections: dict[str, Any] = {}
        self.trace: list[dict[str, Any]] = []
        self.arret: dict[str, Any] | None = None
        self._debut = perf_counter()

    @property
    def demande(self) -> dict[str, Any]:
        """Copie de la demande reçue : personne ne peut modifier l'original."""
        return deepcopy(self._demande)

    @property
    def reference(self) -> str:
        return str(self._demande["reference"])

    def lire(self, section: str) -> Any:
        return deepcopy(self._sections.get(section))

    def enregistrer(self, auteur: str, section: str, valeur: dict[str, Any]) -> None:
        if AUTEURS.get(section) != auteur:
            raise ViolationFrontiere(f"« {auteur} » ne peut pas écrire la section « {section} »")
        if section in self._sections and section not in SECTIONS_VERSIONNEES:
            raise ViolationFrontiere(f"la section « {section} » est déjà définitive")
        self._sections[section] = deepcopy(valeur)

    def noter(
        self,
        agent: str,
        action: str,
        ecrit: list[str],
        duree_ms: float,
        statut: str,
        **details: Any,
    ) -> None:
        """Ajoute une étape à la trace (ajout seul)."""
        self.trace.append(
            {
                "agent": agent,
                "action": action,
                "ecrit": list(ecrit),
                "duree_ms": round(duree_ms, 2),
                "statut": statut,
                **details,
            }
        )

    def ecoule_s(self) -> float:
        return perf_counter() - self._debut
