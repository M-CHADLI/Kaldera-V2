# + · Un modèle de décision « System One »

[← Sommaire](README.md)

## De quoi il s'agit

Jev, de TypeSafe AI, est présenté comme un modèle de décision « System One » ([annonce](https://typesafe.ai/blog/introducing-system-one-models-and-jev), accès anticipé depuis octobre 2026). Contrairement à un LLM qui produit du texte :
- ses **sorties sont typées et choisies dans un ensemble défini à l'avance**, jusqu'à 255 options ;
- chaque sortie est accompagnée d'une **confiance calibrée** ;
- l'éditeur annonce une réponse en **70 à 500 ms**.

Ces chiffres sont ceux de l'éditeur : ils restent à vérifier par notre benchmark.

## Où il a sa place chez Kaldera

La règle : un modèle n'intervient que là où **le champ des possibles est défini** et où **une règle écrite à la main serait fragile**. Il ne décide jamais seul : une confiance trop basse donne `indetermine`, qui mène à une escalade motivée.

| Usage | Sorties possibles | Effet |
|---|---|---|
| **Contrôle de fond du superviseur** | `conforme`, `anomalie`, `indetermine` + confiance | Une anomalie est **signalée** dans la trace et les métriques. Elle ne change aucune valeur : en cas de désaccord, le sous-agent a raison. |
| **Cohérence des pièces avec la déclaration** ([§5, L100-101](../specs_metier.md#L100-L101)) | `coherent`, `incoherent`, `indetermine` + confiance | Sous le seuil de confiance → escalade `gestionnaire` |

**C'est ici que le seuil de confiance prend son sens.** Une confiance qu'un LLM s'attribue à lui-même n'est pas fiable. Une confiance **calibrée** l'est par construction. Le seuil sera fixé par l'épreuve, puis consigné au journal.

## Où il est exclu

| Domaine | Raison |
|---|---|
| Les règles de décision du §10 et les montants | Ce sont des règles chiffrées, testées au centime : le code déterministe est exact par construction |
| L'avis de fraude | La spec l'interdit en interne : « l'avis de fraude est émis par le partenaire, jamais en interne » ([§2, L39](../specs_metier.md#L39)) |

## Les conditions d'intégration

- **Facultatif** : comme le LLM, il n'est jamais nécessaire pour passer les tests.
- **Données minimisées** : envoyer des données à un fournisseur de modèle, c'est les faire sortir de Kaldera. On applique le même filtre que pour le partenaire : pas de données personnelles, pas de description libre.
- **Benchmark comparatif** sur les 28 scénarios rejoués 5 fois :

| Option du superviseur | Mesures |
|---|---|
| Sans modèle (gabarits seuls) | Référence |
| LLM (Kimi-K2.6) | Latence, coût, stabilité, anomalies détectées |
| Modèle System One (Jev) | Mêmes mesures, plus la calibration de la confiance |

## Points de vigilance

- Le produit est en **accès anticipé** : ses performances ne sont pas encore éprouvées hors de l'éditeur.
- C'est une **dépendance à un fournisseur**, avec un nouveau flux de données à déclarer au titre du RGPD.
- Si le modèle est indisponible, le superviseur fonctionne sans lui, comme pour le LLM.
