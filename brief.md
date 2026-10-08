# Kaldera V2 : le brief

## Contexte du projet

Kaldera gère des demandes de remboursement d'assurance. Chaque demande traverse plusieurs métiers : vérifier l'éligibilité, contrôler les pièces justificatives, estimer le montant, et pour les fraudes suspectées, interroger le service anti-fraude d'un partenaire externe (agent A2A). L'agent généraliste actuel mélange les rôles, et surtout : quand le partenaire ne répond pas, toute la demande reste bloquée. Certains clients attendent leur remboursement depuis des semaines.

Le partenaire vient par ailleurs de durcir son contrat d'échange : format strict, données limitées, pas de retry sauvage. La direction des opérations publie donc son cahier d'exigences pour une équipe d'agents digne de ce nom :

- Chaque demande aboutit à une décision ou à une escalade humaine, jamais à un blocage silencieux.
- Chaque agent tient son rôle : l'éligibilité ne fait pas d'estimation, l'estimation ne juge pas la fraude.
- L'équipe tient le choc du réel : partenaire lent, menteur ou en panne : le contrat est respecté à la lettre, et un vrai plan B s'applique.

> **Votre mission : développer cette équipe d'agents de bout en bout, puis la mettre à l'épreuve jusqu'à ce qu'elle tienne.**

## Modalités pédagogiques

### Travail préliminaire de conception

La conception se mène en deux chantiers. La direction des opérations impose les exigences suivantes ; à vous d'en déduire l'architecture :

| | Exigence imposée (direction des opérations) |
|---|---|
| E1 | Toute demande se termine par une décision ou une escalade humaine motivée — jamais un blocage silencieux. |
| E2 | Chaque agent a un rôle et une frontière définis ; aucun agent n'empiète sur le rôle d'un autre. |
| E3 | Seules les données prévues au contrat partent chez le partenaire anti-fraude — rien d'autre. |
| E4 | Une réponse du partenaire non conforme au contrat est rejetée, jamais propagée telle quelle. |
| E5 | Partenaire indisponible → le mode dégradé défini par le métier s'applique (la demande continue ou est routée, selon `specs_metier.md`). |
| E6 | Aucune boucle infinie ; les métriques par agent (latence, échecs, recours à l'externe) sont visibles — et tout ajustement de l'orchestration provoqué par un scénario d'épreuve est consigné. |

#### Chantier 1 : l'équipe & son orchestration

Questions pour guider votre réflexion :

1. Quels agents la spec implique-t-elle (éligibilité, pièces, estimation, coordination) ? Quel est le rôle exact et la frontière de chacun ? Lesquels peuvent travailler en parallèle, lesquels dépendent d'un autre ?
   > ⚠️ **Attention :** la spec laisse au moins un point de frontière ambigu. À vous de le repérer et de trancher.
2. Quel schéma d'orchestration : superviseur qui délègue, chaîne séquentielle, mixte ? Qui décide qu'une demande est terminée ?
3. Quelles bornes fixez-vous a priori pour prévenir boucles et emballements (nombre d'étapes max, délais par agent, conditions d'arrêt) ? Sur quelle base les fixez-vous, sachant qu'elles sont provisoires ? (C'est le chantier 2 qui les éprouvera.)
4. Quelle mémoire partagée pour une demande (état commun) : que contient-elle, où vit-elle, et comment un agent évite-t-il d'écraser le travail d'un autre ?

#### Chantier 2 : la collaboration A2A & l'épreuve du réel

Questions pour guider votre réflexion :

1. Que dit exactement `external_agent/contrat.md` : entrées attendues, sorties, délais, limites d'appel ? Quelles données envoyez-vous au partenaire — et lesquelles ne doivent jamais partir ? Où appliquez-vous ce filtre ?
2. Comment validez-vous une réponse du partenaire avant de la croire (schéma, plausibilité) ? Que faites-vous d'une réponse invalide ou d'un délai dépassé — sachant que le contrat interdit le retry sauvage ?
3. Que prévoit `specs_metier.md` quand le partenaire est indisponible : quelles demandes continuent sans avis fraude, lesquelles partent en file humaine ? Comment l'implémentez-vous sans bloquer le reste ?
4. Comment testez-vous une équipe (et pas un agent isolé) : quels scénarios d'intégration rejouez-vous depuis `eval/scenarios.jsonl` — nominaux, pannes, réponses invalides, piège à boucle ?
5. Quels signaux monitorez-vous par agent (latence, taux d'échec, recours à l'externe, étapes consommées) et, quand un scénario d'épreuve révèle une faiblesse d'orchestration, comment l'ajustement du chantier 1 (borne, frontière, routage) est-il décidé et consigné ?

#### Architecture / schéma attendus

1. **La carte des agents :** rôles, frontières (y compris le point ambigu tranché), dépendances, parallélisme.
2. **Le schéma d'orchestration** (délégations, conditions d'arrêt, bornes provisoires) + le modèle de la mémoire partagée.
3. **Le schéma d'échange A2A :** contrat, filtre de données, validation des réponses, et le chemin de mode dégradé.
4. **Le plan d'épreuve :** scénarios d'intégration × signaux observés × ajustement possible du chantier 1.

> **Livrable de conception :** dossier de conception (carte des agents + orchestration & mémoire partagée + schéma A2A & mode dégradé + plan d'épreuve), **validé par le formateur avant tout code**.

### Développement

#### Chantier 1

- Développer les agents spécialistes et leurs frontières selon la spec.
- Mettre en place l'orchestration : routage, terminaison garantie, bornes provisoires anti-boucle.
- Mettre en place la mémoire partagée de la demande (état commun, accès maîtrisé).

#### Chantier 2

- Brancher la liaison A2A : contrat respecté, filtre des données envoyées, gestion des délais, validation de chaque réponse.
- Implémenter le mode dégradé défini par le métier quand le partenaire est indisponible.
- Écrire les tests d'intégration multi-agents sur `eval/scenarios.jsonl` et instrumenter le monitorage par agent.
- Éprouver l'équipe : rejouer les scénarios de panne, de réponse invalide et de boucle ; ajuster les bornes, frontières ou routages du chantier 1 que l'épreuve révèle insuffisants, et consigner chaque ajustement.

## Modalités d'évaluation

- Validation du dossier de conception (porte d'entrée du brief) : frontières (dont le point ambigu), contrat A2A, mode dégradé et plan d'épreuve sont questionnés.
- Passage des tests d'acceptance fournis + revue d'architecture et de code.
- Auto-évaluation et co-évaluation Simplonline.

## Livrables

1. Dossier de conception (carte des agents + orchestration & mémoire partagée + A2A & mode dégradé + plan d'épreuve).
2. L'équipe d'agents fonctionnelle avec mémoire partagée et collaboration A2A.
3. Les tests d'intégration multi-agents + le monitorage par agent + le journal des ajustements d'orchestration.
4. La preuve d'exécution des tests d'acceptance.

## Critères de performance

- Tous les tests d'acceptance fournis passent.
- Les six exigences de la direction des opérations (E1 à E6) sont respectées et démontrées.
- La collaboration A2A respecte le contrat, valide les réponses et n'envoie que des données autorisées.
- Le mode dégradé préserve le service quand le partenaire est indisponible ; le scénario piège à boucle s'arrête dans les bornes.
- Les bornes et frontières finales sont justifiées par l'épreuve (scénarios rejoués), chaque ajustement consigné (pas de réglage au doigt mouillé).
