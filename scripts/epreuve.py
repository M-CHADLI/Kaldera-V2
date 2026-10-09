"""Banc d'épreuve : rejoue eval/scenarios.jsonl contre le partenaire simulé et relève les signaux.

    uv run python scripts/epreuve.py [--repetitions N] [--sortie docs/epreuve-resultats.md]

Lance son propre partenaire simulé (port libre) ; aucun service externe n'est requis.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn

RACINE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RACINE / "src"), str(RACINE)]
os.environ.setdefault("PARTENAIRE_JETON", "jeton-recette")

import kaldera  # noqa: E402
from external_agent.app import app  # noqa: E402

CHAMPS_ATTENDUS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")


def demarrer_partenaire() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=serveur.run, daemon=True).start()
    while not serveur.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}"


def conforme(fiche: dict[str, Any], attendu: dict[str, Any]) -> bool:
    for champ in CHAMPS_ATTENDUS:
        if champ in attendu and fiche.get(champ) != attendu[champ]:
            return False
    if "avis_fraude" in attendu:
        niveau = (fiche.get("avis_fraude") or {}).get("niveau")
        if niveau != attendu["avis_fraude"]:
            return False
    return not (attendu.get("arret") and not fiche.get("arret"))


def rejouer(url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(base_url=url) as client:
        client.post("/_sim/reset").raise_for_status()
        client.post("/_sim/mode", json=scenario["partenaire"]).raise_for_status()
    debut = time.perf_counter()
    resultat = kaldera.traiter_lot(scenario["demandes"], partenaire_url=url)
    duree = time.perf_counter() - debut
    fiches = resultat["fiches"]
    metriques = resultat["metriques"]
    return {
        "conforme": all(conforme(f, a) for f, a in zip(fiches, scenario["attendu"], strict=True)),
        "etapes_max": max(len(f["trace"]) for f in fiches),
        "duree_lot_s": round(duree, 2),
        "appels_externes": sum(m["appels_externes"] for m in metriques.values()),
        "echecs": sum(m["echecs"] for m in metriques.values()),
        "anomalies": sum(m.get("anomalies", 0) for m in metriques.values()),
        "arrets": ", ".join(sorted({f["arret"]["borne"] for f in fiches if f["arret"]})) or "—",
        "issues": " · ".join(
            f"{f['issue']}{'/' + str(f['file']) if f['file'] else ''}"
            f"{' (dégradé)' if f['mode_degrade'] else ''}"
            for f in fiches
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--sortie", type=Path, default=None)
    args = parser.parse_args()

    url = demarrer_partenaire()
    scenarios = [
        json.loads(ligne)
        for ligne in (RACINE / "eval" / "scenarios.jsonl").read_text(encoding="utf-8").splitlines()
        if ligne.strip()
    ]
    lignes = [
        f"# Résultats d'épreuve · bornes {kaldera.bornes()}",
        "",
        "| Scénario | Conforme | Stable | Étapes max | Durée du lot (s) | Appels externes"
        " | Échecs | Anomalies | Arrêts | Issues |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    total_conformes = 0
    for scenario in scenarios:
        mesures = [rejouer(url, scenario) for _ in range(args.repetitions)]
        stable = len({m["issues"] for m in mesures}) == 1
        m = mesures[-1]
        total_conformes += all(x["conforme"] for x in mesures)
        lignes.append(
            f"| {scenario['id']} | {'oui' if all(x['conforme'] for x in mesures) else 'NON'}"
            f" | {'oui' if stable else 'NON'} | {max(x['etapes_max'] for x in mesures)}"
            f" | {max(x['duree_lot_s'] for x in mesures)} | {m['appels_externes']}"
            f" | {m['echecs']} | {m['anomalies']} | {m['arrets']} | {m['issues']} |"
        )
    lignes += ["", f"**{total_conformes} scénarios conformes sur {len(scenarios)}.**"]
    texte = "\n".join(lignes)
    print(texte)
    if args.sortie:
        args.sortie.write_text(texte + "\n", encoding="utf-8")
    if total_conformes < len(scenarios):
        sys.exit(1)


if __name__ == "__main__":
    main()
