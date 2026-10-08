"""Ce qu'un agent reçoit et renvoie : une vue en lecture seule, un résultat et un statut."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

# conclu : la section est produite ; complement_requis : il manque une pièce (Pièces) ;
# indetermine : l'agent ne peut pas trancher, ce qui mène à une escalade motivée.
STATUTS = ("conclu", "complement_requis", "indetermine")


@dataclass(frozen=True)
class Resultat:
    statut: str
    valeur: dict[str, Any] = field(default_factory=dict)
    motif: str = ""
    appels_externes: int = 0
    echec: bool = False


class Agent(Protocol):
    nom: str
    section: str
    action: str

    def traiter(self, vue: dict[str, Any]) -> Resultat: ...
