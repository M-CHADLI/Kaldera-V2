#!/usr/bin/env python3
"""Pilote en direct le service anti-fraude partenaire simulé.

Exemples :
    python scripts/partner_ctl.py etat
    python scripts/partner_ctl.py normal
    python scripts/partner_ctl.py lent --delai 6
    python scripts/partner_ctl.py invalide --variante niveau_incoherent
    python scripts/partner_ctl.py panne
    python scripts/partner_ctl.py journal
    python scripts/partner_ctl.py reset

URL du partenaire : option ``--url``, sinon ``PARTENAIRE_URL``, sinon http://localhost:8100.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

VARIANTES = (
    "rotation",
    "score_hors_bornes",
    "niveau_incoherent",
    "champ_hors_contrat",
    "reference_differente",
    "champ_absent",
    "non_json",
    "enveloppe_invalide",
)


def appeler(url: str, chemin: str, corps: dict[str, Any] | None = None) -> Any:
    donnees = None if corps is None else json.dumps(corps).encode()
    requete = urllib.request.Request(
        f"{url.rstrip('/')}{chemin}",
        data=donnees,
        method="GET" if corps is None and chemin != "/_sim/reset" else "POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=5) as reponse:
            return json.loads(reponse.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"erreur {exc.code} : {exc.read().decode()}")
    except urllib.error.URLError as exc:
        sys.exit(
            f"partenaire injoignable sur {url} ({exc.reason}) — lancé avec `make partenaire` ou `make up` ?"
        )


def afficher_journal(entrees: list[dict[str, Any]], brut: bool) -> None:
    if brut:
        print(json.dumps(entrees, ensure_ascii=False, indent=2))
        return
    if not entrees:
        print("(journal vide)")
        return
    print(f"{'horodatage':<30} {'mode':<9} {'dossier':<13} {'HTTP':>4}  conforme  détail")
    for e in entrees:
        detail = (
            "doublon"
            if e.get("doublon")
            else (e.get("variante") or json.dumps(e.get("erreurs") or "", ensure_ascii=False))
        )
        print(
            f"{e['horodatage']:<30} {e['mode']:<9} {str(e.get('reference') or '?'):<13} "
            f"{str(e.get('statut_http') or '…'):>4}  {'oui' if e.get('conforme') else 'non':<8}  {detail}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default=os.environ.get("PARTENAIRE_URL", "http://localhost:8100"))
    sous = parser.add_subparsers(dest="commande", required=True)
    sous.add_parser("etat", help="mode courant et nombre d'appels reçus")
    sous.add_parser("normal", help="réponses conformes")
    lent = sous.add_parser("lent", help="réponses conformes mais tardives")
    lent.add_argument(
        "--delai", type=float, default=6.0, help="délai de réponse en secondes (défaut : 6)"
    )
    invalide = sous.add_parser("invalide", help="réponses non conformes au contrat")
    invalide.add_argument("--variante", choices=VARIANTES, default="rotation")
    sous.add_parser("panne", help="service indisponible (HTTP 503)")
    journal = sous.add_parser("journal", help="appels reçus par le partenaire")
    journal.add_argument("--brut", action="store_true", help="journal complet en JSON")
    sous.add_parser("reset", help="vide le journal et oublie les dossiers déjà évalués")
    args = parser.parse_args()

    if args.commande == "etat":
        print(json.dumps(appeler(args.url, "/_sim/etat"), ensure_ascii=False, indent=2))
    elif args.commande == "journal":
        afficher_journal(appeler(args.url, "/_sim/journal"), args.brut)
    elif args.commande == "reset":
        print(json.dumps(appeler(args.url, "/_sim/reset"), ensure_ascii=False, indent=2))
    else:
        reglage: dict[str, Any] = {"mode": args.commande}
        if args.commande == "lent":
            reglage["delai_s"] = args.delai
        if args.commande == "invalide":
            reglage["variante"] = args.variante
        print(json.dumps(appeler(args.url, "/_sim/mode", reglage), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
