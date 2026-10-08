"""Rapport de décision : motive et explique chaque décision (docs/conception/5-rapport-de-decision.md).

Produit de façon déterministe à partir de l'état et de la trace : chaque phrase cite sa règle.
Ne recopie jamais de contenu venant du partenaire, ni de donnée personnelle.
"""

from __future__ import annotations

from typing import Any

from .decision import euros
from .etat import Etat

INDICATEURS = {
    "F1": "montant déclaré d'au moins 5 000 €",
    "F2": "contrat souscrit moins de 90 jours avant le sinistre",
    "F3": "au moins 3 sinistres déclarés sur 12 mois",
    "F4": "montant déclaré supérieur de plus de 20 % au montant justifié",
}
NIVEAUX = {"faible": "faible", "modere": "modéré", "eleve": "élevé"}
DECISIONS = {"acceptee": "ACCEPTÉE", "refusee": "REFUSÉE"}
RAPPEL_PLAFOND = (
    "« Aucune demande ne peut donner lieu à un remboursement supérieur au plafond de sa formule. »"
)


def pour_gestionnaire(etat: Etat) -> str:
    """Rapport complet, destiné au gestionnaire et à l'audit."""
    issue = etat.lire("issue")
    lignes = [f"Rapport de décision · {etat.reference}", f"Issue : {_ligne_issue(issue)}", ""]
    lignes += _eligibilite(etat.lire("eligibilite"))
    lignes += _pieces(etat.lire("pieces"), _complements(etat))
    lignes += _montant(etat.lire("estimation"))
    lignes += _antifraude(etat.lire("avis_fraude"))
    lignes += _decision(issue)
    lignes += ["", _execution(etat, issue)]
    return "\n".join(lignes)


def pour_assure(etat: Etat) -> str:
    """Version courte pour l'assuré : sans le détail du contrôle anti-fraude, information sensible."""
    issue = etat.lire("issue")
    lignes = [f"Votre demande {etat.reference}", f"Issue : {_ligne_issue(issue, assure=True)}", ""]
    lignes += _montant(etat.lire("estimation"), numero="")
    if issue["issue"] == "escalade":
        lignes.append("Votre dossier est transmis à un gestionnaire, qui reviendra vers vous.")
    else:
        lignes.append(f"Motif : {_motif_assure(issue)}")
    return "\n".join(lignes)


def _ligne_issue(issue: dict[str, Any], assure: bool = False) -> str:
    if issue["issue"] == "decision":
        texte = f"décision · {DECISIONS[issue['decision']]} · {euros(issue['montant_rembourse'])}"
    elif assure:
        texte = "en cours d'examen par un gestionnaire"
    else:
        texte = f"escalade · file {issue['file']}"
    if issue.get("mode_degrade") and not assure:
        texte += " · MODE DÉGRADÉ"
    return texte


def _eligibilite(section: dict[str, Any] | None) -> list[str]:
    if not section or "eligible" not in section:
        return ["1. Éligibilité — non examinée ou non concluante."]
    if section["eligible"]:
        return ["1. Éligibilité — éligible : les 5 conditions du §4 sont remplies."]
    return [f"1. Éligibilité — non éligible (§4) : {', '.join(section['motifs'])}."]


def _pieces(section: dict[str, Any] | None, complements: int) -> list[str]:
    if not section or "conformes" not in section:
        return ["2. Pièces — non examinées."]
    demandes = f", {complements} complément(s) demandé(s)" if complements else ""
    if section["conformes"]:
        factures = " + ".join(euros(m) for m in section["factures"]) or "aucune"
        return [f"2. Pièces — complètes{demandes} ; factures lisibles : {factures} (§5)."]
    manquantes = ", ".join(section["a_redemander"])
    return [f"2. Pièces — manquantes ou illisibles : {manquantes}{demandes} (§5)."]


def _montant(section: dict[str, Any] | None, numero: str = "3. ") -> list[str]:
    if not section or "montant_estime" not in section:
        return [f"{numero}Montant — non estimé."]
    franchise = section.get("franchise", 0.0)
    avant_plafond = max(0.0, section["montant_retenu"] - franchise)
    lignes = [
        f"{numero}Montant (§6) —"
        f" déclaré {euros(section.get('montant_declare', section['montant_retenu']))}"
        f" · justifié {euros(section['montant_justifie'])}"
        f" · retenu {euros(section['montant_retenu'])}",
        f"   franchise de la formule {section.get('formule', '')} : − {euros(franchise)}"
        f"   →   {euros(avant_plafond)}",
    ]
    if section["plafond_applique"]:
        lignes += [
            f"   PLAFOND APPLIQUÉ : la formule rembourse au plus {euros(section['plafond'])}"
            " par sinistre (§4).",
            f"   {RAPPEL_PLAFOND}",
        ]
    lignes.append(f"   montant estimé : {euros(section['montant_estime'])}")
    return lignes


def _antifraude(section: dict[str, Any] | None) -> list[str]:
    if not section or "statut" not in section:
        return ["4. Anti-fraude — non examinée."]
    if section["statut"] == "non_requis":
        return ["4. Anti-fraude — non requis : aucun indicateur F1 à F4 (§7)."]
    requis = ", ".join(f"{i} ({INDICATEURS[i]})" for i in section["indicateurs"])
    lignes = [f"4. Anti-fraude — requis : {requis}."]
    if section["statut"] == "obtenu":
        niveau = NIVEAUX.get(section["niveau"], section["niveau"])
        lignes.append(
            f"   Avis du partenaire : risque {niveau}, score {section['score']:.2f}"
            f" (évaluation {section['evaluation_id']})."
        )
    else:
        rejet = section.get("rejet") or {}
        lignes.append(
            f"   Avis indisponible : {rejet.get('raison', 'non obtenu')}"
            f" (couche « {rejet.get('couche', '?')} »). Réponse non recopiée (§7, §9)."
        )
    return lignes


def _decision(issue: dict[str, Any]) -> list[str]:
    regle = f"règle {issue['regle']} du §10" if issue.get("regle") else "interruption"
    return [f"5. Décision — {regle} : {issue['motif']}"]


def _execution(etat: Etat, issue: dict[str, Any]) -> str:
    borne = etat.arret["borne"] if etat.arret else "aucune"
    degrade = "oui" if issue.get("mode_degrade") else "non"
    return f"Exécution : {len(etat.trace)} étape(s) · borne atteinte : {borne} · mode dégradé : {degrade}"


def _complements(etat: Etat) -> int:
    return sum(1 for etape in etat.trace if etape["action"] == "demander_complement")


def _motif_assure(issue: dict[str, Any]) -> str:
    motif = str(issue["motif"])
    return motif.split(" Décision prise sans avis anti-fraude")[0]
