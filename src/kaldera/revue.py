"""Revue de fond facultative du superviseur (docs/conception/, livrables 2 et 6).

Le superviseur contrôle toujours la **forme** des sorties des agents. La revue de **fond**, en
plus, n'est qu'un **signal** : en cas de désaccord, le sous-agent a raison. Aucune valeur n'est
modifiée et l'issue ne change pas. Le signal est noté dans la trace (champ ``revue`` de l'étape),
compté dans les métriques (``anomalies``) et mentionné dans le rapport gestionnaire.

Réviseur choisi par ``KALDERA_REVUE`` :

- ``regles`` (défaut) : contrôles de cohérence déterministes, sans modèle ;
- ``aucune`` : pas de revue ;
- ``llm`` : modèle de langage (``kaldera.llm``), qui ne voit que la section examinée ;
- ``system_one`` : modèle de décision à sorties typées et confiance calibrée (hypothèse).

Quel que soit le réviseur, :func:`reviser` garantit que la revue ne lève jamais d'exception,
ne travaille que sur une copie et ne dépasse jamais le délai qui lui est accordé.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from time import perf_counter
from typing import Any, Callable, Literal, Protocol, get_args

import httpx

from . import llm
from .decision import euros
from .partenaire import niveau_attendu

StatutRevue = Literal["conforme", "anomalie", "indetermine", "indisponible"]
STATUTS_REVUE: tuple[str, ...] = get_args(StatutRevue)
# Ce qu'un modèle peut répondre ; « indisponible » est réservé à Kaldera (erreur, délai…).
VERDICTS = ("conforme", "anomalie", "indetermine")

VARIABLE_REVUE = "KALDERA_REVUE"
VARIABLE_URL = "KALDERA_SYSTEM_ONE_URL"
VARIABLE_CLE = "KALDERA_SYSTEM_ONE_CLE"
VARIABLE_SEUIL = "KALDERA_SEUIL_CONFIANCE"
SEUIL_CONFIANCE = 0.8

DELAI_S = 1.0  # délai d'un réviseur qui n'en déclare pas
TOLERANCE = 0.005  # les montants sont arrondis au centime
LONGUEUR_RAISON_MAX = 200

# Liste blanche des champs qu'un réviseur externe (LLM, System One) reçoit, section par section :
# la section examinée seule, sans identifiant du partenaire ni donnée personnelle.
CHAMPS_TRANSMIS: dict[str, tuple[str, ...]] = {
    "eligibilite": ("eligible", "motifs"),
    "pieces": ("conformes", "a_redemander", "sans_depot", "factures"),
    "estimation": (
        "formule",
        "franchise",
        "montant_declare",
        "montant_justifie",
        "montant_retenu",
        "montant_estime",
        "plafond",
        "plafond_applique",
    ),
    "avis_fraude": ("statut", "indicateurs", "niveau", "score"),
}

# Entrées d'une section lues dans une autre section de l'état : l'estimation est calculée sur
# les factures lisibles retenues par l'agent Pièces (des montants, aucune donnée personnelle).
# Seule RevueRegles s'en sert ; les réviseurs externes ne reçoivent que CHAMPS_TRANSMIS.
ENTREES: dict[str, dict[str, str]] = {"estimation": {"factures": "pieces"}}


@dataclass(frozen=True)
class Signal:
    """Avis de la revue de fond sur une section : un signal, jamais une correction."""

    statut: StatutRevue
    raison: str
    confiance: float | None = None


class Reviseur(Protocol):
    """Examine une section produite par un agent.

    Attributs facultatifs lus par :func:`reviser` : ``nom`` (noté dans la trace) et
    ``delai_s`` (délai accordé à un examen, :data:`DELAI_S` à défaut).
    """

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal: ...


# ---------------------------------------------------------------- exécution sûre


def reviser(
    reviseur: Reviseur,
    section: str,
    valeur: dict[str, Any],
    budget_s: float,
    lire: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Fait examiner une section sans risque pour le traitement ; retourne l'entrée ``revue``.

    - le réviseur reçoit une copie : il ne peut modifier aucune valeur de l'état ni du flux ;
    - aucune exception ne remonte : toute erreur donne ``indisponible`` ;
    - l'examen dure au plus ``min(délai du réviseur, budget_s)`` ; au-delà, le superviseur
      n'attend plus et note ``indisponible``.

    ``lire`` donne accès aux autres sections de l'état, pour les entrées de :data:`ENTREES`.
    """
    debut = perf_counter()
    try:
        examinee = a_examiner(section, valeur, lire)
        signal = _examiner_borne(reviseur, section, examinee, min(_delai(reviseur), budget_s))
    except Exception as exc:  # noqa: BLE001 — la revue ne gêne jamais le traitement
        signal = Signal("indisponible", f"revue impossible ({type(exc).__name__})")
    return {
        "reviseur": _nom(reviseur),
        **asdict(signal),
        "duree_ms": round((perf_counter() - debut) * 1000, 2),
    }


def a_examiner(
    section: str, valeur: dict[str, Any], lire: Callable[[str], Any] | None = None
) -> dict[str, Any]:
    """Copie de la section produite, complétée des entrées qu'elle a lues dans l'état."""
    examinee = deepcopy(valeur)
    for champ, source in ENTREES.get(section, {}).items():
        depuis = lire(source) if lire else None
        if isinstance(depuis, dict) and champ in depuis and champ not in examinee:
            examinee[champ] = deepcopy(depuis[champ])
    return examinee


def champs_transmis(section: str, valeur: dict[str, Any]) -> dict[str, Any]:
    """Ce qu'un réviseur externe a le droit de voir : la liste blanche de la section."""
    return {c: deepcopy(valeur[c]) for c in CHAMPS_TRANSMIS.get(section, ()) if c in valeur}


def _examiner_borne(
    reviseur: Reviseur, section: str, valeur: dict[str, Any], delai_s: float
) -> Signal:
    """Examen dans un fil séparé : le superviseur n'attend jamais plus de ``delai_s``."""
    if delai_s <= 0:
        return Signal("indisponible", "budget de temps réservé au traitement : revue non faite")
    rendu: list[Any] = []

    def examiner() -> None:
        try:
            rendu.append(reviseur.examiner(section, valeur))
        except BaseException as exc:  # noqa: BLE001 — rapportée comme indisponible
            rendu.append(exc)

    # Fil « daemon » : un réviseur bloqué ne retient ni la demande ni l'arrêt du processus.
    fil = threading.Thread(target=examiner, name=f"revue-{section}", daemon=True)
    fil.start()
    fil.join(delai_s)
    if not rendu:
        return Signal("indisponible", f"revue non rendue en {delai_s:.2g} s")
    signal = rendu[0]
    if isinstance(signal, BaseException):
        return Signal("indisponible", f"réviseur en erreur ({type(signal).__name__})")
    if not _signal_conforme(signal):
        return Signal("indisponible", "signal du réviseur non conforme")
    return replace(signal, raison=_abreger(signal.raison))


def _signal_conforme(signal: Any) -> bool:
    return (
        isinstance(signal, Signal)
        and signal.statut in STATUTS_REVUE
        and isinstance(signal.raison, str)
        and (signal.confiance is None or _est_probabilite(signal.confiance))
    )


def _delai(reviseur: Reviseur) -> float:
    delai = getattr(reviseur, "delai_s", DELAI_S)
    return float(delai) if _est_nombre(delai) else DELAI_S


def _nom(reviseur: Reviseur) -> str:
    nom = getattr(reviseur, "nom", None)
    return nom if isinstance(nom, str) else type(reviseur).__name__


# ------------------------------------------------------- réviseur par défaut


class RevueRegles:
    """Contrôles de cohérence de fond, déterministes et sans modèle (réviseur par défaut).

    Ne recalcule pas le travail des agents : vérifie des invariants entre les champs d'une
    section. Une section inconnue, incomplète ou mal typée donne ``indetermine``.
    """

    nom = "regles"
    delai_s = 0.5

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        controle = CONTROLES.get(section)
        if controle is None:
            return Signal("indetermine", f"aucun contrôle de fond pour la section « {section} »")
        try:
            ecarts = controle(valeur)
        except (KeyError, TypeError, ValueError):
            return Signal("indetermine", f"section « {section} » incomplète ou mal typée")
        if ecarts:
            return Signal("anomalie", " ; ".join(ecarts))
        return Signal("conforme", "contrôles de cohérence satisfaits")


def _controler_eligibilite(valeur: dict[str, Any]) -> list[str]:
    eligible, motifs = _booleen(valeur["eligible"]), _liste(valeur["motifs"])
    if eligible and motifs:
        return ["demande éligible portant des motifs de refus"]
    if not eligible and not motifs:
        return ["demande non éligible sans motif"]
    return []


def _controler_pieces(valeur: dict[str, Any]) -> list[str]:
    conformes, a_redemander = _booleen(valeur["conformes"]), _liste(valeur["a_redemander"])
    ecarts = []
    if conformes and a_redemander:
        ecarts.append("pièces déclarées conformes alors que des pièces sont à redemander")
    if not conformes and not a_redemander:
        ecarts.append("pièces déclarées non conformes sans pièce à redemander")
    if any(_nombre(f) < 0 for f in _liste(valeur["factures"])):
        ecarts.append("facture de montant négatif")
    return ecarts


def _controler_estimation(valeur: dict[str, Any]) -> list[str]:
    justifie, retenu = _nombre(valeur["montant_justifie"]), _nombre(valeur["montant_retenu"])
    estime, plafond = _nombre(valeur["montant_estime"]), _nombre(valeur["plafond"])
    applique = _booleen(valeur["plafond_applique"])
    ecarts = []
    if "factures" in valeur:
        total = round(sum(_nombre(f) for f in _liste(valeur["factures"])), 2)
        if abs(justifie - total) > TOLERANCE:
            ecarts.append(
                f"montant justifié {euros(justifie)} différent de la somme des factures"
                f" {euros(total)}"
            )
    if "montant_declare" in valeur:
        attendu = min(_nombre(valeur["montant_declare"]), justifie)
        if abs(retenu - attendu) > TOLERANCE:
            ecarts.append("montant retenu différent du plus petit du déclaré et du justifié")
    if estime < 0:
        ecarts.append("montant estimé négatif")
    if estime > plafond + TOLERANCE:
        ecarts.append(f"montant estimé {euros(estime)} supérieur au plafond {euros(plafond)}")
    if estime > retenu + TOLERANCE:
        ecarts.append(f"montant estimé {euros(estime)} supérieur au montant retenu {euros(retenu)}")
    avant_plafond = max(0.0, retenu - _nombre(valeur.get("franchise", 0.0)))
    depasse = avant_plafond > plafond + TOLERANCE
    if applique and not depasse:
        ecarts.append(
            f"plafond signalé appliqué alors que le montant avant plafond"
            f" {euros(avant_plafond)} ne le dépasse pas"
        )
    elif applique and abs(estime - plafond) > TOLERANCE:
        ecarts.append("plafond signalé appliqué mais montant estimé différent du plafond")
    elif depasse and not applique:
        ecarts.append(
            f"plafond non signalé alors que le montant avant plafond {euros(avant_plafond)}"
            f" dépasse le plafond {euros(plafond)}"
        )
    return ecarts


def _controler_avis(valeur: dict[str, Any]) -> list[str]:
    statut, indicateurs = valeur["statut"], _liste(valeur["indicateurs"])
    if statut not in ("non_requis", "obtenu", "indisponible"):
        return ["statut d'avis inconnu"]
    if statut == "non_requis":
        return ["avis non requis malgré des indicateurs F1 à F4"] if indicateurs else []
    ecarts = [] if indicateurs else ["partenaire consulté sans indicateur F1 à F4"]
    if statut == "obtenu":
        # Valeurs du partenaire jamais recopiées dans la raison (rapport, §7).
        score = _nombre(valeur["score"])
        if not 0 <= score <= 1:
            ecarts.append("score de l'avis hors de l'intervalle [0 ; 1]")
        elif valeur["niveau"] != niveau_attendu(score):
            ecarts.append("niveau de l'avis incohérent avec son score")
    return ecarts


CONTROLES: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "eligibilite": _controler_eligibilite,
    "pieces": _controler_pieces,
    "estimation": _controler_estimation,
    "avis_fraude": _controler_avis,
}


# ----------------------------------------------------------- réviseur LLM


CONSIGNE_LLM = (
    "Tu relis une section produite par un agent de traitement des demandes de remboursement "
    "d'assurance habitation. Vérifie seulement sa cohérence interne (montants, booléens, "
    "listes). Tu ne corriges rien. Réponds uniquement par un objet JSON "
    '{"statut": "conforme" | "anomalie" | "indetermine", "raison": "<une phrase>"}.'
)


class RevueLLM:
    """Revue par le modèle de langage de ``kaldera.llm`` (facultative).

    Ne lui transmet que la section examinée, réduite à sa liste blanche : jamais la demande
    brute, jamais de donnée personnelle, jamais la réponse brute du partenaire. Toute erreur,
    réponse illisible ou dépassement de délai donne ``indisponible``. La confiance qu'un LLM
    s'attribue n'étant pas calibrée, elle n'est pas demandée (livrable 6).
    """

    nom = "llm"
    delai_s = 2.0

    def __init__(self, delai_s: float | None = None) -> None:
        if delai_s is not None:
            self.delai_s = delai_s
        self._modele: Any = None

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        donnees = champs_transmis(section, valeur)
        if not donnees:
            return Signal("indetermine", f"aucun champ transmissible pour la section « {section} »")
        messages = [
            ("system", CONSIGNE_LLM),
            ("human", json.dumps({"section": section, "valeur": donnees}, ensure_ascii=False)),
        ]
        try:
            if self._modele is None:
                self._modele = llm.get_llm()
            reponse = self._modele.invoke(messages)
        except (TimeoutError, httpx.TimeoutException):
            return Signal("indisponible", "modèle de langage : aucune réponse dans le délai")
        except Exception as exc:  # noqa: BLE001 — un modèle absent ou en panne n'est qu'un signal
            return Signal("indisponible", f"modèle de langage indisponible ({type(exc).__name__})")
        return lire_verdict(getattr(reponse, "content", reponse))


def lire_verdict(contenu: Any) -> Signal:
    """Lit la réponse ``{"statut", "raison"}`` d'un modèle ; sinon ``indisponible``."""
    illisible = Signal("indisponible", "réponse du modèle illisible")
    if not isinstance(contenu, str):
        return illisible
    debut, fin = contenu.find("{"), contenu.rfind("}")
    if not 0 <= debut < fin:
        return illisible
    try:
        verdict = json.loads(contenu[debut : fin + 1])
    except ValueError:
        return illisible
    if (
        not isinstance(verdict, dict)
        or verdict.get("statut") not in VERDICTS
        or not isinstance(verdict.get("raison"), str)
    ):
        return illisible
    return Signal(verdict["statut"], _abreger(verdict["raison"]))


# -------------------------------------------------- réviseur « System One »


class RevueSystemOne:
    """Point d'extension, **hypothèse** : modèle de décision « System One » (livrable 6).

    Sorties typées choisies dans un ensemble fixé d'avance, avec une confiance calibrée.
    Contrat supposé, à confirmer avec l'éditeur avant tout branchement réel :

    - requête : ``POST KALDERA_SYSTEM_ONE_URL``, en-tête ``Authorization: Bearer
      KALDERA_SYSTEM_ONE_CLE``, corps ``{"tache", "section", "valeur", "sorties"}`` où
      ``valeur`` est la section réduite à sa liste blanche (données minimisées) ;
    - réponse : ``{"statut": "conforme" | "anomalie" | "indetermine", "confiance": 0..1}``.

    Une confiance sous ``KALDERA_SEUIL_CONFIANCE`` (0,8 par défaut, à fixer par l'épreuve)
    donne ``indetermine``. Délai court (1 s) ; toute erreur donne ``indisponible``.
    """

    nom = "system_one"
    delai_s = 1.0

    def __init__(
        self,
        url: str | None = None,
        cle: str | None = None,
        seuil: float | None = None,
        delai_s: float | None = None,
    ) -> None:
        self.url = url if url is not None else os.environ.get(VARIABLE_URL, "")
        self.cle = cle if cle is not None else os.environ.get(VARIABLE_CLE, "")
        self.seuil = seuil if seuil is not None else seuil_confiance()
        if delai_s is not None:
            self.delai_s = delai_s

    def examiner(self, section: str, valeur: dict[str, Any]) -> Signal:
        if not self.url:
            return Signal("indisponible", f"{VARIABLE_URL} non renseignée")
        try:
            return self._interroger(section, valeur)
        except httpx.TimeoutException:
            return Signal("indisponible", f"System One : aucune réponse en {self.delai_s:g} s")
        except Exception as exc:  # noqa: BLE001 — un modèle injoignable n'est qu'un signal
            return Signal("indisponible", f"System One injoignable ({type(exc).__name__})")

    def _interroger(self, section: str, valeur: dict[str, Any]) -> Signal:
        corps = {
            "tache": "revue_de_fond",
            "section": section,
            "valeur": champs_transmis(section, valeur),
            "sorties": list(VERDICTS),
        }
        reponse = httpx.post(
            self.url,
            json=corps,
            headers={"Authorization": f"Bearer {self.cle}"},
            timeout=self.delai_s,
        )
        if reponse.status_code != 200:
            return Signal("indisponible", f"System One : statut HTTP {reponse.status_code}")
        try:
            verdict = reponse.json()
        except ValueError:
            verdict = None
        if (
            not isinstance(verdict, dict)
            or verdict.get("statut") not in VERDICTS
            or not _est_probabilite(verdict.get("confiance"))
        ):
            return Signal("indisponible", "System One : réponse illisible")
        statut, confiance = verdict["statut"], float(verdict["confiance"])
        if confiance < self.seuil:
            return Signal(
                "indetermine",
                f"System One : confiance {confiance:.2f} sous le seuil {self.seuil:.2f}",
                confiance,
            )
        return Signal(statut, f"System One : {statut} (confiance {confiance:.2f})", confiance)


def seuil_confiance() -> float:
    """Seuil lu dans ``KALDERA_SEUIL_CONFIANCE`` (virgule acceptée) ; 0,8 s'il est invalide."""
    brut = os.environ.get(VARIABLE_SEUIL, "").strip().replace(",", ".")
    try:
        seuil = float(brut) if brut else SEUIL_CONFIANCE
    except ValueError:
        return SEUIL_CONFIANCE
    return seuil if 0 <= seuil <= 1 else SEUIL_CONFIANCE


# --------------------------------------------------------------- sélection


def choisir_reviseur(choix: str | None = None) -> Reviseur | None:
    """Réviseur selon ``KALDERA_REVUE`` : ``regles`` (défaut), ``aucune``, ``llm``, ``system_one``.

    Une valeur vide ou inconnue donne le défaut sûr, ``regles``.
    """
    valeur = choix if choix is not None else os.environ.get(VARIABLE_REVUE, "")
    valeur = valeur.strip().lower().replace("-", "_")
    if valeur == "aucune":
        return None
    if valeur == "llm":
        return RevueLLM()
    if valeur == "system_one":
        return RevueSystemOne()
    return RevueRegles()


# ------------------------------------------------------------------ outils


def _est_nombre(valeur: Any) -> bool:
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def _est_probabilite(valeur: Any) -> bool:
    return _est_nombre(valeur) and 0 <= valeur <= 1


def _nombre(valeur: Any) -> float:
    if not _est_nombre(valeur):
        raise TypeError("montant non numérique")
    return float(valeur)


def _booleen(valeur: Any) -> bool:
    if not isinstance(valeur, bool):
        raise TypeError("valeur non booléenne")
    return valeur


def _liste(valeur: Any) -> list[Any]:
    if not isinstance(valeur, list):
        raise TypeError("valeur non listée")
    return valeur


def _abreger(texte: str) -> str:
    """Une ligne, bornée : la raison est reprise telle quelle dans la trace et le rapport."""
    ligne = " ".join(texte.split())
    if len(ligne) <= LONGUEUR_RAISON_MAX:
        return ligne
    return ligne[: LONGUEUR_RAISON_MAX - 1].rstrip() + "…"
