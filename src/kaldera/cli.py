"""Rejoue des demandes : ``python -m kaldera.cli eval/scenarios.jsonl [--scenario ID]``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import traiter_lot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fichier", type=Path, help="fichier JSONL de scénarios")
    parser.add_argument("--scenario", action="append", help="identifiant(s) de scénario à rejouer")
    parser.add_argument("--partenaire", default=None, help="URL du partenaire anti-fraude")
    parser.add_argument("--trace", action="store_true", help="affiche la trace de chaque fiche")
    args = parser.parse_args()

    for ligne in args.fichier.read_text(encoding="utf-8").splitlines():
        if not ligne.strip():
            continue
        scenario = json.loads(ligne)
        if args.scenario and scenario["id"] not in args.scenario:
            continue
        print(f"== {scenario['id']} — {scenario['titre']}")
        resultat = traiter_lot(scenario["demandes"], partenaire_url=args.partenaire)
        for fiche in resultat["fiches"]:
            if not args.trace:
                fiche = {k: v for k, v in fiche.items() if k != "trace"}
            print(json.dumps(fiche, ensure_ascii=False))
        print(json.dumps({"metriques": resultat["metriques"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
