# 4 · Plan d'épreuve

[← Sommaire](README.md)

## La méthode

- **On teste l'équipe, pas un agent isolé.** Les 28 scénarios de [scenarios.jsonl](../../eval/scenarios.jsonl) sont rejoués de bout en bout via `traiter_demande` et `traiter_lot`, contre le partenaire simulé ([external_agent/app.py](../../external_agent/app.py)), piloté par [partner_ctl.py](../../scripts/partner_ctl.py).
- **Deux niveaux de tests :**
  - la suite d'acceptance fournie ([tests/acceptance/](../../tests/acceptance/)), lancée par `make test` ;
  - nos tests d'intégration, qui vérifient en plus les règles de la trace, les bornes, le rapport de décision et l'absence de données personnelles dans l'historique.
- **Stabilité** : si un LLM ou un modèle System One est branché, chaque scénario est rejoué 5 fois. La fiche doit rester identique d'une exécution à l'autre.

## Avant / après

| Mesure | Code fourni (avant) | Équipe (après) |
|---|---|---|
| Tests d'acceptance réussis | [à mesurer avec `make test`] | 100 % visés |
| Fiches `en_attente` (blocages silencieux) | [à mesurer] | 0 |
| Champs hors contrat envoyés au partenaire | Toute la demande | 0 |
| Durée maximale d'une demande | Illimitée (`timeout=None`) | ≤ 8 s |

## Scénarios × signaux × ajustements

| Scénarios | Ce qu'on éprouve | Signal surveillé | Ajustement possible (chantier 1) |
|---|---|---|---|
| NOM-01 à 11 | Les règles métier | Issue et montant comparés à l'attendu | Frontière (exemple : le plafond dans NOM-05) |
| NOM-07 + BCL-01 | La boucle de compléments | Étapes consommées, compléments, `arret` | `complements_max`, `etapes_max` |
| AF-01 à 07 | Le recours au partenaire | `appels_externes` de l'Anti-fraude, comparés au nombre de demandes avec F1 à F4 | Condition d'appel (routage) |
| INV-01 à 07 | La validation des réponses | `echecs` de l'Anti-fraude, `mode_degrade`, aucune trace de `EVA-NC` dans la fiche | Couche de validation |
| PAN-01 | La panne pendant un lot | `echecs`, appels pendant la panne | `disjoncteur_echecs` |
| PAN-02 | La lenteur pendant un lot | Latence p95 comparée à 8 s, durée totale du lot | `delai_partenaire_s`, `duree_max_s`, parallélisme |
| Tous | Le superviseur et son modèle facultatif | Anomalies signalées, latence du superviseur | Périmètre du contrôle de fond |

**Justifier les bornes.** NOM-07 fixe le minimum de compléments : sa demande doit aboutir après un complément. BCL-01 fixe le maximum : la boucle doit s'arrêter, avec `arret` rempli. Une valeur choisie entre les deux est justifiée par l'épreuve.

## Les signaux par agent

Les métriques sont renvoyées par `traiter_lot()["metriques"]` ([interface.md:58-68](../interface.md#L58-L68)) :

| Métrique | Sens |
|---|---|
| `appels` | Étapes réalisées par l'agent |
| `echecs` | Étapes en échec : erreur, délai dépassé, réponse rejetée |
| `latence_ms` | Durée moyenne d'une étape |
| `appels_externes` | Appels au partenaire |
| `etapes` (ajout) | Étapes consommées par demande, comparées à `etapes_max` |
| `anomalies` (ajout) | Anomalies signalées par le superviseur |

## La règle d'ajustement

1. Un signal anormal mène à une hypothèse sur sa cause.
2. On ne change **qu'une seule chose** : une borne, une frontière ou un routage.
3. On rejoue **les 28 scénarios**, pas seulement celui qui échouait.
4. On garde le changement si rien ne casse ; sinon, on l'annule.
5. On le consigne au journal, **même s'il a été annulé**.

## Le journal des ajustements

Il sera tenu dans `docs/journal-ajustements.md` pendant le développement :

| Date | Scénario | Signal observé | Cause | Ajustement (borne, frontière ou routage) | Preuve avant / après | Gardé ? |
|---|---|---|---|---|---|---|
| | | | | | | |
