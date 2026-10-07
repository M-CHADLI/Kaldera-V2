# Kaldera

Plateforme de traitement des demandes de remboursement d'assurance habitation :
contrôle d'éligibilité, vérification des pièces justificatives, estimation du
montant et consultation d'un service anti-fraude partenaire selon le protocole
agent-à-agent (A2A).

## Features

- Traitement d'une demande ou d'un lot de demandes jusqu'à une fiche de décision
  (décision ou escalade vers une file humaine).
- Règles métier chiffrées : formules, franchises, plafonds, seuils d'escalade.
- Demandes de complément de pièces via l'espace assuré.
- Consultation du service anti-fraude partenaire (JSON-RPC 2.0, Agent Card).
- Service partenaire simulé, pilotable en direct (normal, lent, invalide, panne).
- Jeu de scénarios de recette et suite d'acceptance.

## Stack

- Python 3.11 (uv)
- FastAPI 0.115+ / uvicorn 0.30+ (service partenaire simulé)
- httpx 0.27+ (client A2A)
- pydantic 2.x
- LangChain 0.3.x, langchain-azure-ai 0.1.x (Kimi-K2.6), LangGraph 0.2.x
- pytest 8.x
- Docker Compose (service partenaire)

## Setup

```bash
make install              # uv sync — installe les dépendances
cp .env.example .env      # puis renseigner les valeurs
make up                   # docker compose up -d — service partenaire sur :8100
make test                 # suite d'acceptance (lance son propre partenaire simulé)
```

Sans Docker, le service partenaire se lance aussi en local : `make partenaire`.

## Utilisation

```bash
make scenarios                                    # rejoue eval/scenarios.jsonl
make scenarios ARGS="--scenario NOM-01 --trace"   # un scénario, avec sa trace
make ctl ARGS=panne                               # met le service partenaire en panne
make ctl ARGS=journal                             # appels reçus par le partenaire
```

Les cibles `make` chargent `.env`. Hors `make` : `set -a; . ./.env; set +a`.

## Layout

- `src/kaldera/` — traitement des demandes (orchestrateur, agent, client partenaire, espace assuré, règles)
- `docs/specs_metier.md` — spécifications fonctionnelles
- `docs/interface.md` — contrat d'intégration (points d'entrée, fiche de décision, trace, métriques)
- `external_agent/` — service anti-fraude partenaire simulé et son contrat d'échange (`contrat.md`)
- `scripts/partner_ctl.py` — pilotage du service partenaire simulé
- `eval/scenarios.jsonl` — scénarios de recette
- `tests/acceptance/` — suite d'acceptance

## Useful commands

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make down       # arrête les services docker
```

## Known issues

- Les échanges avec le service anti-fraude n'ont pas été revalidés depuis la
  version 2.0 de son contrat.
- Le comportement face à un partenaire lent ou indisponible n'a pas encore été
  éprouvé en conditions réelles.

## License

Usage interne — tous droits réservés.
