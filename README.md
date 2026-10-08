# Kaldera

[![CI](https://github.com/M-CHADLI/Kaldera-V2/actions/workflows/ci.yml/badge.svg)](https://github.com/M-CHADLI/Kaldera-V2/actions/workflows/ci.yml)

Plateforme de traitement des demandes de remboursement d'assurance habitation par une
**équipe d'agents** : contrôle d'éligibilité, vérification des pièces justificatives,
estimation du montant et consultation d'un service anti-fraude partenaire selon le
protocole agent-à-agent (A2A). Chaque demande finit par une décision ou une escalade
motivée, expliquée dans un rapport, même quand le partenaire est lent, menteur ou en panne.

## Features

- Quatre agents spécialistes et un superviseur-décideur à ordre fixe ; chaque section
  de l'état partagé a un seul auteur, tracé (`docs/conception/`).
- Règles de décision du §10 en code déterministe, mode dégradé du §9 compris.
- Bornes d'exécution exposées par `kaldera.bornes()` : compléments, dépôt identique,
  étapes, durée ; toute interruption donne une escalade avec `arret` rempli.
- Client A2A conforme au contrat v2.0 : 7 champs en liste blanche, un appel par dossier,
  abandon à 3 s, validation en trois couches, disjoncteur par lot.
- Rapport de décision par demande, en deux versions (gestionnaire, assuré).
- Console web : rejouer les scénarios, piloter le partenaire simulé, lire fiches,
  rapports, traces et métriques par agent.
- Banc d'épreuve et journal des ajustements d'orchestration.

## Stack

- Python 3.11 (uv)
- FastAPI 0.115+ / uvicorn 0.30+ (console web et service partenaire simulé)
- httpx 0.27+ (client A2A)
- LangChain 0.3.x, langchain-azure-ai 0.1.x (Kimi-K2.6), facultatif
- pytest 8.x, pytest-cov (couverture minimale : 85 %)
- Docker Compose (console + partenaire simulé)
- GitHub Actions (qualité, tests, épreuve, déploiement de test)

## Setup

```bash
make install              # uv sync — installe les dépendances
cp .env.example .env      # puis renseigner les valeurs
make test                 # acceptance + tests unitaires (lance son propre partenaire simulé)
```

## Utilisation

```bash
make up                                           # console sur :8000, partenaire sur :8100
make web                                          # console seule, en local (avec make partenaire)
make scenarios ARGS="--scenario NOM-01 --trace"   # un scénario en ligne de commande
make epreuve                                      # 28 scénarios × 3, écrit docs/epreuve-resultats.md
make cov                                          # couverture, rapport HTML dans htmlcov/
make ctl ARGS=panne                               # met le service partenaire en panne
```

Les cibles `make` chargent `.env`. Hors `make` : `set -a; . ./.env; set +a`.

## Layout

- `src/kaldera/superviseur.py` — orchestration à ordre fixe, bornes, contrôle de forme, conclusion
- `src/kaldera/agents/` — éligibilité, pièces, estimation, anti-fraude
- `src/kaldera/etat.py`, `vues.py` — état partagé (un seul écrivain) et vues par agent
- `src/kaldera/decision.py`, `rapport.py` — règles du §10 et rapport de décision
- `src/kaldera/partenaire.py` — client A2A (liste blanche, délai, validation, disjoncteur)
- `src/kaldera/web.py`, `console.html` — console web
- `docs/conception/` — dossier de conception ; `docs/journal-ajustements.md` — journal
- `external_agent/` — service anti-fraude partenaire simulé et son contrat (`contrat.md`)
- `eval/scenarios.jsonl` — scénarios de recette ; `scripts/epreuve.py` — banc d'épreuve
- `tests/acceptance/` — suite d'acceptance fournie ; `tests/unit/` — tests unitaires

## Intégration continue

`.github/workflows/ci.yml`, à chaque push et pull request :

1. **Qualité** : ruff (lint et format), mypy.
2. **Tests** : acceptance et unitaires, couverture minimale 85 % ; banc d'épreuve ;
   preuves d'exécution (couverture, rapport JUnit, résultats d'épreuve) en artefacts.
3. **Déploiement de test** : `docker compose up`, contrôle de santé, rejeu de PAN-01
   sur la pile déployée.

## License

Usage interne — tous droits réservés.
