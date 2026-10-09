# 4 · Plan d'épreuve

[← Sommaire](README.md)

## La méthode

- **On teste l'équipe, pas un agent isolé.** Les 28 scénarios de [scenarios.jsonl](../../eval/scenarios.jsonl) sont rejoués de bout en bout via `traiter_demande` et `traiter_lot`, contre le partenaire simulé ([external_agent/app.py](../../external_agent/app.py)), piloté par ses routes `/_sim/*` (ou par [partner_ctl.py](../../scripts/partner_ctl.py) à la main).
- **Deux niveaux de tests :**
  - la suite d'acceptance fournie ([tests/acceptance/](../../tests/acceptance/)), 56 tests, lancée par `make test` ;
  - nos tests unitaires et d'intégration ([tests/unit/](../../tests/unit/)), 287 tests, qui vérifient en plus les règles de la trace, les bornes, le rapport de décision, la revue de fond, notre partenaire maison et l'absence de données personnelles dans l'historique.
- **Le banc d'épreuve** ([scripts/epreuve.py](../../scripts/epreuve.py)) rejoue les 28 scénarios **3 fois** (`make epreuve`, et à chaque push en CI), avec la revue de fond par défaut (`regles`). Un scénario est stable si ses issues sont identiques d'un rejeu à l'autre.
- **Stabilité avec un modèle** : si un LLM ou un modèle System One est branché, on prévoit 5 rejeux (`--repetitions 5`). Ce rejeu n'a pas encore été fait.
- **Contre le partenaire réel** : la console déployée (livrable 3) rejoue un scénario contre notre partenaire, sans réglage possible et une seule fois par dossier.

## Avant / après

| Mesure | Code fourni (avant) | Équipe (après) |
|---|---|---|
| Tests d'acceptance réussis | **11 / 56** | **56 / 56** |
| Tests au total (acceptance + unitaires) | 56 | **343**, couverture 98,43 % (lignes et branches) |
| Scénarios conformes à l'attendu (banc d'épreuve, 3 rejeux) | — | **28 / 28**, stables |
| Anomalies signalées par la revue de fond (`regles`) | — | **0** sur 28 scénarios × 3 rejeux |
| Fiches `en_attente` (blocages silencieux) | BCL-01 et toute demande sans avis du partenaire | 0 |
| Champs hors contrat envoyés au partenaire | Toute la demande | 0 |
| Durée maximale d'un lot | Illimitée (`timeout=None`) | 3,07 s observées sur PAN-02 (borne par demande : 8 s) |

Le détail des ajustements est dans le [journal](../journal-ajustements.md), les mesures dans [epreuve-resultats.md](../epreuve-resultats.md), et la preuve d'exécution dans [preuves-execution.md](../preuves-execution.md).

## Scénarios × signaux × ajustements

| Scénarios | Ce qu'on éprouve | Signal surveillé | Ajustement possible (chantier 1) |
|---|---|---|---|
| NOM-01 à 11 | Les règles métier | Issue et montant comparés à l'attendu | Frontière (exemple : le plafond dans NOM-05) |
| NOM-07 + BCL-01 | La boucle de compléments | Étapes consommées, compléments, `arret` | `complements_max`, `etapes_max` |
| AF-01 à 07 | Le recours au partenaire | `appels_externes` de l'Anti-fraude, comparés au nombre de demandes avec F1 à F4 | Condition d'appel (routage) |
| INV-01 à 07 | La validation des réponses | `echecs` de l'Anti-fraude, `mode_degrade`, aucune trace de `EVA-NC` dans la fiche | Couche de validation |
| PAN-01 | La panne pendant un lot | `echecs`, appels pendant la panne | `disjoncteur_echecs` |
| PAN-02 | La lenteur pendant un lot | Latence p95 comparée à 8 s, durée totale du lot | `delai_partenaire_s`, `duree_max_s`, parallélisme |
| Tous | Le superviseur et sa revue de fond facultative | Anomalies signalées, durée de la revue | Périmètre du contrôle de fond |

**Justifier les bornes.** NOM-07 fixe le minimum de compléments : sa demande doit aboutir après un complément. BCL-01 fixe le maximum : la boucle doit s'arrêter, avec `arret` rempli. Une valeur choisie entre les deux est justifiée par l'épreuve.

## Les signaux par agent

Les métriques sont renvoyées par `traiter_lot()["metriques"]` ([interface.md:58-68](../interface.md#L58-L68), [metriques.py](../../src/kaldera/metriques.py)) :

| Métrique | Sens |
|---|---|
| `appels` | Étapes réalisées par l'agent |
| `echecs` | Étapes en échec : erreur, délai dépassé, réponse rejetée |
| `latence_ms` | Durée moyenne d'une étape |
| `appels_externes` | Appels au partenaire |
| `anomalies` (ajout) | Signaux `anomalie` de la revue de fond du superviseur, sur les sections produites par l'agent |

Les **étapes consommées par demande** ne sont pas une métrique par agent : le banc d'épreuve les lit dans la longueur de la trace (colonne « Étapes max »), et les compare à `etapes_max`.

## La règle d'ajustement

1. Un signal anormal mène à une hypothèse sur sa cause.
2. On ne change **qu'une seule chose** : une borne, une frontière ou un routage.
3. On rejoue **les 28 scénarios**, pas seulement celui qui échouait.
4. On garde le changement si rien ne casse ; sinon, on l'annule.
5. On le consigne au journal, **même s'il a été annulé**.

## Le journal des ajustements

Il est tenu dans [journal-ajustements.md](../journal-ajustements.md), une ligne par signal observé :

| Date | Scénario | Signal observé | Cause | Ajustement (borne, frontière ou routage) | Preuve avant / après | Gardé ? |
|---|---|---|---|---|---|---|

Un signal qui ne demande aucun ajustement est consigné lui aussi, avec « Aucun » dans la colonne Ajustement.
