"""Orchestration du traitement d'une demande de remboursement."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Protocol

from .agent_generaliste import AgentGeneraliste

MAX_TOURS = 50


class Agent(Protocol):
    nom: str

    def prochaine_action(self, etat: dict[str, Any]) -> str | None: ...

    def executer(self, action: str, etat: dict[str, Any]) -> list[str]: ...


class Orchestrateur:
    """Confie chaque action à l'agent désigné par la table de routage et journalise
    qui a fait quoi."""

    ACTIONS = (
        "verifier_eligibilite",
        "verifier_pieces",
        "demander_complement",
        "estimer",
        "consulter_partenaire",
        "conclure",
    )

    def __init__(self, partenaire_url: str | None = None) -> None:
        generaliste = AgentGeneraliste(partenaire_url)
        self.agents: dict[str, Agent] = {generaliste.nom: generaliste}
        self.routage: dict[str, str] = {action: generaliste.nom for action in self.ACTIONS}
        self.planificateur: Agent = generaliste

    def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
        etat: dict[str, Any] = {"demande": demande, "trace": []}
        for _ in range(MAX_TOURS):
            action = self.planificateur.prochaine_action(etat)
            if action is None:
                break
            nom_agent = self.routage[action]
            debut = perf_counter()
            ecrit = self.agents[nom_agent].executer(action, etat)
            etat["trace"].append(
                {
                    "agent": nom_agent,
                    "action": action,
                    "ecrit": ecrit,
                    "duree_ms": round((perf_counter() - debut) * 1000, 2),
                }
            )
        return construire_fiche(etat)


def construire_fiche(etat: dict[str, Any]) -> dict[str, Any]:
    demande = etat["demande"]
    issue = etat.get("issue") or {
        "issue": "en_attente",
        "decision": None,
        "montant_rembourse": None,
        "motif": "",
        "file": None,
    }
    return {
        "reference": demande["reference"],
        **issue,
        "avis_fraude": etat.get("avis_fraude"),
        "trace": etat["trace"],
    }
