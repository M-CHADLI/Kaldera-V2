# + · Un modèle de décision « System One »

[← Sommaire](README.md)

## De quoi il s'agit

Jev, de TypeSafe AI, est présenté comme un modèle de décision « System One » ([annonce](https://typesafe.ai/blog/introducing-system-one-models-and-jev), accès anticipé depuis octobre 2026). Contrairement à un LLM qui produit du texte :
- ses **sorties sont typées et choisies dans un ensemble défini à l'avance**, jusqu'à 255 options ;
- chaque sortie est accompagnée d'une **confiance calibrée** ;
- l'éditeur annonce une réponse en **70 à 500 ms**.

Ces chiffres sont ceux de l'éditeur : ils restent à vérifier par notre benchmark.

## Où il a sa place chez Kaldera

La règle : un modèle n'intervient que là où **le champ des possibles est défini** et où **une règle écrite à la main serait fragile**. Il ne décide jamais seul : une confiance trop basse donne `indetermine`. Pour un agent, `indetermine` mène à une escalade motivée ; pour la revue de fond, ce n'est qu'un signal.

| Usage | Sorties possibles | Effet | État |
|---|---|---|---|
| **Contrôle de fond du superviseur** | `conforme`, `anomalie`, `indetermine` + confiance | Une anomalie est **signalée** dans la trace et les métriques. Elle ne change aucune valeur : en cas de désaccord, le sous-agent a raison. | Point d'extension codé, en **hypothèse** (voir plus bas) |
| **Cohérence des pièces avec la déclaration** ([§5, L100-101](../specs_metier.md#L100-L101)) | `coherent`, `incoherent`, `indetermine` + confiance | Sous le seuil de confiance → escalade `gestionnaire` | Non implémenté |

**C'est ici que le seuil de confiance prend son sens.** Une confiance qu'un LLM s'attribue à lui-même n'est pas fiable. Une confiance **calibrée** l'est par construction. Le seuil vaut 0,8 par défaut (`KALDERA_SEUIL_CONFIANCE`). Il reste à fixer par l'épreuve, puis à consigner au journal.

## Le point d'extension `system_one`

Avec `KALDERA_REVUE=system_one`, la revue de fond passe par la classe `RevueSystemOne` ([revue.py:371-444](../../src/kaldera/revue.py#L371-L444)). **C'est une hypothèse** : aucun service réel n'est branché, et le contrat d'appel est supposé, à confirmer avec l'éditeur.

| Élément | Contrat supposé |
|---|---|
| Requête | `POST` sur `KALDERA_SYSTEM_ONE_URL`, en-tête `Authorization: Bearer` avec `KALDERA_SYSTEM_ONE_CLE` ; corps `{tache, section, valeur, sorties}`, où `valeur` est la section réduite à sa liste blanche |
| Réponse | `{statut, confiance}` : `statut` parmi `conforme`, `anomalie`, `indetermine` ; `confiance` entre 0 et 1 |
| Seuil | Confiance sous `KALDERA_SEUIL_CONFIANCE` → `indetermine` |
| Délai | 1 s ; toute erreur, réponse illisible ou URL absente → `indisponible` |

Sans URL, chaque examen rend `indisponible` : le traitement continue, l'issue ne change pas.

## Où il est exclu

| Domaine | Raison |
|---|---|
| Les règles de décision du §10 et les montants | Ce sont des règles chiffrées, testées au centime : le code déterministe est exact par construction |
| L'avis de fraude | La spec l'interdit en interne : « l'avis de fraude est émis par le partenaire, jamais en interne » ([§2, L39](../specs_metier.md#L39)) |

## Les conditions d'intégration

- **Facultatif** : comme le LLM, il n'est jamais nécessaire pour passer les tests.
- **Données minimisées** : envoyer des données à un fournisseur de modèle, c'est les faire sortir de Kaldera. On applique le même principe que pour le partenaire : une liste blanche par section ([revue.py:50-66](../../src/kaldera/revue.py#L50-L66)), pas de données personnelles, pas de description libre.
- **Benchmark comparatif** sur les 28 scénarios rejoués 5 fois. À ce jour, seule la référence est mesurée :

| Option du superviseur (`KALDERA_REVUE`) | Mesures | État au 9 octobre 2026 |
|---|---|---|
| Sans modèle (`regles`) | Référence | Mesurée sur 3 rejeux : 28/28 conformes et stables, 0 anomalie sur 348 examens, durée médiane d'un examen 0,5 ms (mesure locale) |
| LLM (`llm`, Kimi-K2.6) | Latence, coût, stabilité, anomalies détectées | Non mesuré |
| Modèle System One (`system_one`, Jev) | Mêmes mesures, plus la calibration de la confiance | Non mesuré : aucun service branché |

## Points de vigilance

- Le produit est en **accès anticipé** : ses performances ne sont pas encore éprouvées hors de l'éditeur.
- C'est une **dépendance à un fournisseur**, avec un nouveau flux de données à déclarer au titre du RGPD.
- Si le modèle est indisponible, le superviseur fonctionne sans lui, comme pour le LLM.
