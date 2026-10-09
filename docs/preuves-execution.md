# Preuve d'exécution des tests d'acceptance

Livrable 4 du [brief](../brief.md#L85). Mesures relevées le **9 octobre 2026** sur la branche `integration-projet`, en local (Windows 11, Python 3.11.15), sur l'arbre de travail du jour, qui n'est pas encore commité. La CI les refera au prochain push (voir plus bas).

## Avant / après

| Mesure | Code fourni (commit `b28793b`) | Équipe d'agents (9 octobre 2026) |
|---|---|---|
| Tests d'acceptance réussis | **11 / 56** (45 échecs) | **56 / 56** |
| Tests au total | 56 | **343** réussis (56 d'acceptance + 287 unitaires) |
| Couverture de `kaldera` (lignes et branches) | — | **98,43 %** (seuil bloquant : 85 %) |
| ruff (lint et format), mypy | — | Aucune erreur |
| Banc d'épreuve, 3 rejeux | — | **28 / 28** scénarios conformes et stables |
| Anomalies signalées par la revue de fond (`regles`) | — | **0** sur 28 scénarios × 3 rejeux |

La suite d'acceptance, les scénarios (`eval/`) et le partenaire simulé (`external_agent/`) sont identiques entre le commit `b28793b` et la branche : la comparaison porte bien sur le même banc.

## Comment l'« avant » a été mesuré

Le code fourni est extrait du commit `b28793b` dans un dossier temporaire, sans toucher au dépôt, puis sa suite d'acceptance est lancée avec l'environnement Python du projet. La configuration pytest du commit (`pythonpath = ["src", "."]`) fait importer le code extrait, pas celui de la branche.

```bash
mkdir -p /tmp/avant && git archive b28793b | tar -x -C /tmp/avant
cd /tmp/avant && "<dépôt>/.venv/Scripts/python" -m pytest tests/acceptance -q -p no:cacheprovider
# 45 failed, 11 passed
```

## Détail des tests (après)

| Fichier | Tests |
|---|---|
| [tests/acceptance/test_collaboration_a2a.py](../tests/acceptance/test_collaboration_a2a.py) | 16 |
| [tests/acceptance/test_equipe_orchestration.py](../tests/acceptance/test_equipe_orchestration.py) | 40 |
| [tests/unit/test_equipe.py](../tests/unit/test_equipe.py) | 29 |
| [tests/unit/test_historique.py](../tests/unit/test_historique.py) | 12 |
| [tests/unit/test_interfaces.py](../tests/unit/test_interfaces.py) | 23 |
| [tests/unit/test_partenaire.py](../tests/unit/test_partenaire.py) | 33 |
| [tests/unit/test_partenaire_antifraude.py](../tests/unit/test_partenaire_antifraude.py) | 13 |
| [tests/unit/test_revue.py](../tests/unit/test_revue.py) | 92 |
| [tests/unit/test_extraction.py](../tests/unit/test_extraction.py) | 85 |
| **Total** | **343** |

Couverture : 1 542 instructions, 17 non couvertes ; 496 branches, 15 partielles. Tous les modules sont à 100 %, sauf `extraction.py` (97 %, des cas limites de lecture), `cli.py` (90 %), `llm.py` (60 %, la connexion réelle à Azure AI) et `web.py` (97 %, le réglage du partenaire simulé par HTTP).

## Banc d'épreuve

Résultats complets : [epreuve-resultats.md](epreuve-resultats.md), produit par `make epreuve`.

| Signal | Valeur observée | Borne ou attendu |
|---|---|---|
| Scénarios conformes | 28 / 28, sur chacun des 3 rejeux | 28 / 28 |
| Scénarios stables (mêmes issues à chaque rejeu) | 28 / 28 | 28 / 28 |
| Étapes au plus pour une demande | 7 (NOM-07, PAN-01) | `etapes_max` = 12 |
| Durée au plus d'un lot | 3,07 s (PAN-02, partenaire lent) | `duree_max_s` = 8 s par demande |
| Appels externes par passage | 18 (AF : 7, INV : 7, PAN-01 : 2, PAN-02 : 2) | Un par demande avec F1 à F4 |
| Échecs de l'Anti-fraude par passage | 11 (INV : 7, PAN-01 : 2, PAN-02 : 2) | Rejet ou panne, puis mode dégradé |
| Arrêts par borne | BCL-01 : `depot_identique` | BCL-01 seulement |
| Revue de fond | 348 examens sur 3 rejeux, tous `conforme`, 0 anomalie | Signal seul |

Le décompte de la revue de fond sur les trois rejeux a été fait par un script à part : le tableau d'`epreuve-resultats.md` n'affiche que les anomalies du dernier rejeu.

## Commandes pour reproduire

```bash
uv run pytest -q -p no:cacheprovider --cov=kaldera   # 343 passed ; Total coverage: 98.43%
uv run pytest tests/acceptance -q -p no:cacheprovider  # 56 passed
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run python scripts/epreuve.py --repetitions 3       # 28 scénarios conformes sur 28
make epreuve                                           # idem, et écrit docs/epreuve-resultats.md
```

Aucun service externe n'est requis : les tests et le banc lancent leur propre partenaire simulé, sur un port libre.

## Intégration continue

Le workflow [ci.yml](../.github/workflows/ci.yml) lance à chaque push la qualité, les tests avec la couverture, le banc d'épreuve et un déploiement de test Docker Compose. Il dépose les preuves en artefact `preuves-execution` (`coverage.xml`, `rapport-tests.xml`, `epreuve-resultats.md`).

Dernier run vert : [run 37771464271](https://github.com/M-CHADLI/Kaldera-V2/actions/runs/37771464271), le 8 octobre 2026, sur le commit `cba9881`. Les trois jobs sont verts. **Ce run précède** la revue de fond, l'historique neutralisé et notre partenaire maison : il comptait 129 tests, une couverture de 98,58 % et 28 / 28 scénarios conformes. Les chiffres de cette page sont ceux de l'arbre de travail du 9 octobre ; la CI les mesurera au prochain push.

## Environnement Google Cloud

Partenaire et console déployés sur Cloud Run le 9 octobre 2026 (livrable 3, [section déploiement](conception/3-a2a-mode-degrade.md#notre-partenaire-anti-fraude-et-son-déploiement)).

**Vérifications rejouées le 9 octobre 2026** pendant la rédaction de cette page. Elles se font sans jeton et ne modifient pas l'état des services.

| Vérification | Attendu | Observé |
|---|---|---|
| `GET` partenaire `/health` | 200 | 200, `{"statut":"ok","version_modele":"kaldera-af-1.0.0"}` |
| `GET` partenaire `/_sim/etat` | 404 : aucune route de simulation | 404 |
| `POST` partenaire `/_sim/reset` | 404 | 404 |
| `POST` partenaire `/a2a` sans jeton | 401 | 401, `{"detail":"jeton absent ou invalide"}` |
| `GET` console `/api/sante` | Partenaire réel en ligne | `"partenaire":"en ligne"`, `"type":"réel"` |
| `GET` console `/api/bornes` | Bornes en vigueur | Identiques à `kaldera.bornes()` |
| `POST` console `/api/scenarios/PAN-01/rejouer?mode=panne` | 409 : on ne force pas une panne sur le service réel | 409 |

**Vérifications faites au déploiement, avec le jeton.** Elles ne sont pas rejouées ici, car elles exigent le jeton, qui n'est pas reproduit dans la documentation.

| Vérification | Observé |
|---|---|
| Requête avec un champ interdit (IBAN) | `-32602`, données non conformes |
| Second appel pour un même dossier | `-32029` : avis indisponible côté Kaldera, donc mode dégradé ([journal](journal-ajustements.md), entrée 9) |

Ces deux comportements sont aussi couverts par les tests unitaires de notre partenaire ([test_partenaire_antifraude.py:71-101](../tests/unit/test_partenaire_antifraude.py#L71-L101)).

Pour rejouer les vérifications sans jeton :

```bash
P=https://partenaire-antifraude-oesi5cx3mq-od.a.run.app
C=https://kaldera-console-oesi5cx3mq-od.a.run.app
curl -s "$P/health"
curl -s -o /dev/null -w "%{http_code}\n" "$P/_sim/etat"                                   # 404
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" -d '{}' "$P/a2a"   # 401
curl -s "$C/api/sante"                                                                    # "type":"réel"
curl -s -o /dev/null -w "%{http_code}\n" -X POST -d '' "$C/api/scenarios/PAN-01/rejouer?mode=panne"   # 409
```

Le frontal de Cloud Run exige un `Content-Length` sur un `POST` : d'où le `-d ''`. Le premier appel peut être lent, le temps que le service sorte de veille.
