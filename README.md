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
  abandon à 3 s, validation en trois couches, registre anti-doublon et disjoncteur
  limités au lot.
- Rapport de décision par demande, en deux versions (gestionnaire, assuré).
- Revue de fond facultative du superviseur : un signal noté dans la trace et compté
  dans les métriques (`anomalies`), qui ne modifie jamais une valeur.
- Historique neutralisé facultatif (JSONL) : liste blanche des champs, `id_client`
  pseudonymisé par HMAC.
- Notre propre partenaire anti-fraude (`partenaire_antifraude/`), conforme au contrat
  v2.0, sans routes de simulation, avec un score explicable par règles.
- Analyse de dossier : le contrat, la déclaration, les factures, les photos et le dépôt de plainte
  sont importés pièce par pièce (ou en un seul PDF) ; un agent d'extraction produit la demande
  au format du §3 et une fiche à valider avant tout traitement. Rien n'est conservé.
- Console web : importer les pièces du dossier, rejouer les scénarios (repliés), piloter le partenaire simulé, lire fiches,
  rapports, traces et métriques par agent ; elle reconnaît un partenaire simulé, réel
  ou injoignable.
- Déploiement sur Google Cloud Run (partenaire et console) ; banc d'épreuve et journal
  des ajustements d'orchestration.

## Stack

- Python 3.11 (uv)
- FastAPI 0.115+ / uvicorn 0.30+ (console web, partenaire simulé, partenaire maison)
- httpx 0.27+ (client A2A)
- LangChain 0.3.x (`langchain-openai`, Azure OpenAI gpt-5.4-mini), facultatif : revue de fond `llm` et extraction de dossier
- pytest 8.x, pytest-cov (couverture minimale : 85 %)
- Docker Compose (console + partenaire simulé)
- Google Cloud Run et Artifact Registry, région `europe-west9` (Paris)
- GitHub Actions (qualité, tests, épreuve, déploiement de test)

## Setup

```bash
make install              # uv sync — installe les dépendances
cp .env.example .env      # puis renseigner les valeurs
make test                 # acceptance + tests unitaires (lance son propre partenaire simulé)
```

### Variables d'environnement

Toutes sont listées dans [`.env.example`](.env.example). Aucune n'est nécessaire pour
`make test` ni pour `make epreuve`.

| Variable | Rôle | Par défaut |
|---|---|---|
| `PARTENAIRE_URL` | URL de base du partenaire anti-fraude | `http://localhost:8100` |
| `PARTENAIRE_JETON` | Jeton Bearer du partenaire (lu par le client, le simulateur et notre partenaire) | vide |
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `AZURE_OPENAI_API_VERSION` | Modèle de langage (Azure OpenAI, gpt-5.4-mini), utilisé par la revue `llm` et l'extraction `llm` ou `auto` ; la version d'API est ignorée avec un endpoint `/openai/v1` | vides |
| `KALDERA_LLM_DELAI_S` | Délai maximal d'un appel au modèle, en secondes | `60` |
| `KALDERA_REVUE` | Revue de fond : `regles`, `aucune`, `llm` ou `system_one` | `regles` |
| `KALDERA_SYSTEM_ONE_URL`, `KALDERA_SYSTEM_ONE_CLE` | Service « System One » de la revue `system_one` (hypothèse, aucun service branché) | vides |
| `KALDERA_SEUIL_CONFIANCE` | Seuil de confiance de la revue `system_one` | `0.8` |
| `KALDERA_HISTORIQUE` | Chemin du fichier JSONL de l'historique neutralisé ; vide = désactivé | vide |
| `KALDERA_CLE_HMAC` | Clé HMAC de pseudonymisation de `id_client` ; sans clé, `client` vaut `null` | vide |
| `KALDERA_EXTRACTION` | Extraction du dossier : `champs` (lecture déterministe), `llm` (modèle, strict) ou `auto` (modèle puis repli) | `champs` |
| `KALDERA_SCENARIOS` | Fichier de scénarios lu par la console | `eval/scenarios.jsonl` |
| `APP_ENV`, `LOG_LEVEL` | Réservées ; le code ne les lit pas à ce jour | — |

## Utilisation

```bash
make up                                           # console sur :8000, partenaire simulé sur :8100
make web                                          # console seule, en local (avec make partenaire)
uv run python -m kaldera.extraction exemples/dossier-exemple.pdf --traiter   # un PDF → fiche + décision
make scenarios ARGS="--scenario NOM-01 --trace"   # un scénario en ligne de commande
make epreuve                                      # 28 scénarios × 3, écrit docs/epreuve-resultats.md
make cov                                          # couverture, rapport HTML dans htmlcov/
make ctl ARGS=panne                               # met le service partenaire simulé en panne
```

Les cibles `make` chargent `.env`. Hors `make` : `set -a; . ./.env; set +a`.

Notre partenaire anti-fraude, en local (il exige `PARTENAIRE_JETON`, le même que celui
de la console) :

```bash
set -a; . ./.env; set +a
uv run uvicorn partenaire_antifraude.app:app --port 8200
make web PARTENAIRE_URL=http://localhost:8200     # dans un autre terminal : console branchée dessus
```

## Déploiement (Google Cloud Run)

Déployé le 9 octobre 2026, projet `project-dcb41d07-e852-4bf6-85f`, région `europe-west9`,
images dans le dépôt Artifact Registry `kaldera` :

| Service | URL |
|---|---|
| Partenaire anti-fraude | https://partenaire-antifraude-oesi5cx3mq-od.a.run.app |
| Console, branchée sur ce partenaire | https://kaldera-console-oesi5cx3mq-od.a.run.app |

```bash
PROJET=<id-du-projet> ./scripts/deployer_partenaire.sh
PROJET=<id-du-projet> PARTENAIRE_URL=<url> PARTENAIRE_JETON=<jeton> ./scripts/deployer_console.sh
```

- Les scripts construisent l'image **en local avec Docker**, puis la poussent dans
  Artifact Registry : `gcloud run deploy --source` échoue sur ce projet, car le compte de
  service de Cloud Build n'a pas les droits nécessaires.
- `deployer_partenaire.sh` génère un jeton s'il n'est pas fourni et l'affiche à la fin ;
  il le passe au service en variable d'environnement. Ne le versionnez pas.
- Le partenaire tourne avec `--max-instances 1` : son registre anti-doublon vit en mémoire.
- Face au partenaire réel, la console refuse de forcer une panne (HTTP 409) ; un second
  rejeu du même scénario déclenche le doublon `-32029`, donc le mode dégradé.

Détails et limites : [docs/conception/3-a2a-mode-degrade.md](docs/conception/3-a2a-mode-degrade.md#notre-partenaire-anti-fraude-et-son-déploiement).

## Layout

- `src/kaldera/superviseur.py` — orchestration à ordre fixe, bornes, contrôle de forme, conclusion
- `src/kaldera/agents/` — éligibilité, pièces, estimation (plafond compris), anti-fraude (F1 à F4)
- `src/kaldera/etat.py`, `vues.py` — état partagé (un seul écrivain) et vues par agent
- `src/kaldera/decision.py`, `bornes.py` — règles du §10 et bornes d'exécution
- `src/kaldera/rapport.py` — rapport de décision (gestionnaire, assuré)
- `src/kaldera/revue.py` — revue de fond facultative (`regles`, `llm`, `system_one`, `aucune`)
- `src/kaldera/historique.py` — historique neutralisé (JSONL, pseudonymisation HMAC)
- `src/kaldera/metriques.py` — métriques par agent, `anomalies` comprises
- `src/kaldera/partenaire.py` — client A2A (liste blanche, délai, validation, registre et disjoncteur par lot)
- `src/kaldera/extraction.py` — agent d'analyse de dossier (PDF, images) : extracteurs, validation, fiche
- `src/kaldera/web.py`, `console.html` — console web
- `exemples/` — dossier PDF et pièces d'exemple (données fictives) ; `scripts/exemple_dossier_pdf.py` les génère
- `partenaire_antifraude/` — notre partenaire anti-fraude, déployable sur Cloud Run
- `external_agent/` — service anti-fraude partenaire simulé et son contrat (`contrat.md`)
- `eval/scenarios.jsonl` — scénarios de recette ; `scripts/epreuve.py` — banc d'épreuve
- `scripts/deployer_partenaire.sh`, `deployer_console.sh` — déploiement Cloud Run ; `partner_ctl.py` — pilotage du simulateur
- `tests/acceptance/` — suite d'acceptance fournie (56 tests) ; `tests/unit/` — tests unitaires (287)
- `docs/conception/` — dossier de conception ; `docs/journal-ajustements.md` — journal
- `docs/epreuve-resultats.md` — dernière épreuve ; `docs/preuves-execution.md` — preuve d'exécution

## Intégration continue

`.github/workflows/ci.yml`, à chaque push sur `main` et `integration-projet`, et à chaque
pull request :

1. **Qualité** : ruff (lint et format), mypy.
2. **Tests** : acceptance et unitaires, couverture minimale 85 % ; banc d'épreuve ;
   preuves d'exécution (couverture, rapport JUnit, résultats d'épreuve) en artefacts.
3. **Déploiement de test** : `docker compose up`, contrôle de santé, rejeu de PAN-01
   sur la pile déployée.

Résultats et commandes pour reproduire : [docs/preuves-execution.md](docs/preuves-execution.md).

## License

Usage interne — tous droits réservés.
