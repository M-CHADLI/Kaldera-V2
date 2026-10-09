# Kaldera V2 : dossier de conception

**Version :** 9 octobre 2026, branche `integration-projet`. Rédigé avant le code, puis mis à jour pour correspondre au code livré.

## En une phrase

L'agent généraliste est remplacé par **une équipe de quatre spécialistes et un superviseur-décideur à ordre fixe**. Chaque demande finit par une décision ou une escalade motivée, **expliquée dans un rapport**, même quand le partenaire anti-fraude est lent, menteur ou en panne.

```mermaid
flowchart LR
  D[(Demande)] --> S{{"Superviseur-décideur<br/>ordre fixe · bornes · règles §10 en code"}}
  S -->|vue| E[Éligibilité]
  S -->|vue| P[Pièces]
  S -->|vue| M[Estimation]
  S -->|vue réduite| F[Anti-fraude]
  F <-->|"A2A · 7 champs · 3 s"| X[["Partenaire externe<br/>simulé ou maison (Cloud Run)"]]
  E & P & M & F -.->|résultat + statut| S
  S --> T[("État centralisé<br/>5 sections + trace")]
  T --> FI[/Fiche de décision/]
  T --> R[/Rapport de décision/]
  FI --> H[("Historique neutralisé<br/>facultatif")]
  L(["Revue de fond facultative<br/>règles · LLM · System One"]) -.->|signale, ne modifie rien| S
```

## Les livrables

| # | Livrable | Contenu |
|---|---|---|
| 1 | [Carte des agents](1-carte-des-agents.md) | Rôles, vues, frontières (dont le point ambigu tranché), dépendances, parallélisme |
| 2 | [Orchestration et mémoire partagée](2-orchestration-memoire.md) | Déroulé, conditions d'arrêt, bornes, état partagé, trace, historique, revue de fond |
| 3 | [A2A et mode dégradé](3-a2a-mode-degrade.md) | Contrat, filtre des données, validation, arbre de décision, sécurité, partenaire maison et déploiement, évolutions du contrat |
| 4 | [Plan d'épreuve](4-plan-epreuve.md) | Scénarios × signaux × ajustements, règle d'ajustement, journal |
| + | [Rapport de décision](5-rapport-de-decision.md) | Un rapport qui motive et explique chaque décision |
| + | [Modèle de décision System One](6-modele-system-one.md) | Où un modèle comme Jev a sa place, et où il est exclu ; point d'extension en hypothèse |

La preuve d'exécution des tests d'acceptance est dans [preuves-execution.md](../preuves-execution.md).

## Décisions clés

| Sujet | Décision | Raison |
|---|---|---|
| Équipe | 4 spécialistes + 1 superviseur-décideur | Un agent par section métier ([interface.md:41-44](../interface.md#L41-L44)) |
| Orchestration | Workflow codé à ordre fixe, arrêt dès qu'une règle conclut | Terminaison garantie (E1), aucun appel inutile au partenaire (E3) |
| Règles §10 | Code déterministe ; aucun modèle ne fixe une valeur | Les tests passent sans modèle, montants exacts au centime |
| Point ambigu | Le plafond (§4) est appliqué par l'Estimation, signalé et rappelé dans le motif | NOM-05 attend 3 000 €, alors que le code fourni refusait la demande |
| État | Centralisé, un seul écrivain, auteur tracé, moindre privilège | E2 vérifiable par le code |
| Partenaire | 7 champs en liste blanche, 1 appel, abandon à 3 s, validation en 3 couches | Contrat v2.0 |
| Mode dégradé | §9 de la spec, plus un disjoncteur par lot | E5 |
| Bornes | 2 compléments maximum, arrêt si le dépôt est identique, `etapes_max` = 12, `duree_max_s` = 8 | Fixées a priori, confirmées sans changement par l'épreuve ([journal](../journal-ajustements.md), entrée 6) |
| Revue de fond | Facultative, `regles` par défaut (`KALDERA_REVUE`) ; un signal, jamais une correction | Le sous-agent a raison en cas de désaccord ; l'issue ne dépend d'aucun modèle |
| Historique | JSONL neutralisé, activé par `KALDERA_HISTORIQUE` ; `id_client` pseudonymisé par HMAC | Audit a posteriori sans données personnelles |
| Déploiement | Notre partenaire anti-fraude et la console sur Cloud Run, à Paris (`europe-west9`) | Éprouver la liaison A2A contre un service réel, sans routes de simulation |

## Point de départ : le code fourni

Le code fourni (commit [`b28793b`](https://github.com/M-CHADLI/Kaldera-V2/tree/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera)) enfreignait chacune des six exigences. C'est notre « avant » : **11 tests d'acceptance sur 56** réussissaient ([preuves d'exécution](../preuves-execution.md)). Ses fichiers `orchestrateur.py` et `agent_generaliste.py` n'existent plus sur la branche : les liens ci-dessous pointent vers ce commit.

| Défaut | Où (code fourni) | Exigence |
|---|---|---|
| Un seul agent écrit les 5 sections | [orchestrateur.py:35-38](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/orchestrateur.py#L35-L38) | E2 |
| Toute la demande est envoyée au partenaire, IBAN compris | [partenaire.py:31](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/partenaire.py#L31) | E3 |
| La réponse est recopiée sans validation | [partenaire.py:42](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/partenaire.py#L42) | E4 |
| Appel sans délai maximal (`timeout=None`) | [partenaire.py:38](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/partenaire.py#L38) | E1, E5 |
| Partenaire muet → fiche `en_attente` | [agent_generaliste.py:21](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/agent_generaliste.py#L21), [L124](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/agent_generaliste.py#L124) | E1 |
| Plafond traité comme un motif de refus | [agent_generaliste.py:70-71](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/agent_generaliste.py#L70-L71) | Point ambigu |
| Boucle de compléments sans `arret` ; `MAX_TOURS = 50` | [orchestrateur.py:10](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/orchestrateur.py#L10) | E6 |
| Ni `mode_degrade`, ni `bornes()`, ni métriques par agent | [__init__.py](https://github.com/M-CHADLI/Kaldera-V2/blob/b28793b0c09c4e34403b33d077ce0f31204cb04a/src/kaldera/__init__.py) | E5, E6 |

**Note de vocabulaire :** la spec numérote aussi « E1 à E5 » ses conditions d'éligibilité (§4). Dans ce dossier, **E1 à E6 désignent toujours les exigences de la direction des opérations**. Les conditions d'éligibilité sont appelées « conditions 1 à 5 du §4 ».
