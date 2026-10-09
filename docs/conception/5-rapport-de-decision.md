# + · Le rapport de décision

[← Sommaire](README.md)

## Pourquoi

La fiche de décision ([§11](../specs_metier.md#L196-L209)) donne l'issue et un motif d'une ligne. Ça ne suffit pas pour un gestionnaire qui reprend un dossier, pour un assuré qui conteste, ni pour un contrôle a posteriori du mode dégradé. **Chaque demande produit donc un rapport qui motive et explique sa décision**, étape par étape, en citant la règle appliquée.

## Ce qu'il contient

| Partie | Contenu | Auteur de l'information |
|---|---|---|
| Issue | Décision ou escalade, montant, file, motif, mode dégradé | Superviseur-décideur |
| Éligibilité | Résultat, et la condition du §4 qui a échoué s'il y en a une | Éligibilité |
| Pièces | Pièces complètes ou manquantes, factures lisibles, nombre de compléments demandés | Pièces |
| Montant | Le calcul complet : déclaré, justifié, retenu, franchise, **plafond s'il s'applique, avec le rappel de la règle** | Estimation |
| Anti-fraude | Indicateurs F1 à F4 relevés, statut de l'avis (niveau, score, `evaluation_id`), couche de validation qui a échoué le cas échéant | Anti-fraude |
| Règle du §10 | Le numéro de la règle qui a fixé l'issue, ou « interruption » | Superviseur-décideur |
| Exécution | Étapes consommées, borne atteinte le cas échéant, mode dégradé | Superviseur |
| Revue de fond | Anomalies signalées, « aucune anomalie » ou « non effectuée » ; un signal, sans effet sur l'issue | Superviseur (revue de fond) |

## Comment il est produit

- **De façon déterministe**, à partir de l'état et de la trace, avec un gabarit par partie ([rapport.py](../../src/kaldera/rapport.py)). Chaque partie cite sa règle (une section de la spec ou du §10).
- **Aucun LLM ne rédige le rapport.** La conception initiale prévoyait une reformulation facultative par un LLM, contrôlée par une vérification des montants et des numéros de règle. **Elle n'a pas été implémentée.** Le seul usage d'un LLM est la revue de fond `llm` (livrable 2).
- Le rapport ne recopie jamais de contenu venant du partenaire au-delà des valeurs validées (niveau, score, `evaluation_id`), ni aucune donnée personnelle.
- **Deux versions** :
  - **gestionnaire** : le rapport complet ;
  - **assuré** : l'issue, le calcul du montant et le motif. Une escalade y est présentée comme « en cours d'examen par un gestionnaire ». Cette version ne contient **ni le détail du contrôle anti-fraude**, qui est une information sensible, ni la mention du mode dégradé, ni la revue de fond.

La fiche porte les deux versions, dans les champs `rapport` et `rapport_assure`. Seul `rapport` est conservé dans l'historique neutralisé (livrable 2).

Les exemples ci-dessous sont des sorties réelles, produites le 9 octobre 2026 en rejouant les scénarios contre le partenaire simulé, avec la revue de fond par défaut.

## Exemple 1 · le plafond appliqué (NOM-05)

```
Rapport de décision · KAL-26-0105
Issue : décision · ACCEPTÉE · 3 000,00 €

1. Éligibilité — éligible : les 5 conditions du §4 sont remplies.
2. Pièces — complètes ; factures lisibles : 4 200,00 € (§5).
3. Montant (§6) — déclaré 4 200,00 € · justifié 4 200,00 € · retenu 4 200,00 €
   franchise de la formule essentiel : − 300,00 €   →   3 900,00 €
   PLAFOND APPLIQUÉ : la formule rembourse au plus 3 000,00 € par sinistre (§4).
   « Aucune demande ne peut donner lieu à un remboursement supérieur au plafond de sa formule. »
   montant estimé : 3 000,00 €
4. Anti-fraude — non requis : aucun indicateur F1 à F4 (§7).
5. Décision — règle 6 du §10 : Remboursement accordé : 3 000,00 €. Plafond de la formule essentiel atteint : aucun remboursement ne peut dépasser 3 000,00 € par sinistre (§4).

Exécution : 5 étape(s) · borne atteinte : aucune · mode dégradé : non
Revue de fond : aucune anomalie.
```

## Exemple 2 · le mode dégradé (INV-01)

Version gestionnaire :

```
Rapport de décision · KAL-26-0301
Issue : décision · ACCEPTÉE · 1 050,00 € · MODE DÉGRADÉ

1. Éligibilité — éligible : les 5 conditions du §4 sont remplies.
2. Pièces — complètes ; factures lisibles : 1 200,00 € (§5).
3. Montant (§6) — déclaré 1 200,00 € · justifié 1 200,00 € · retenu 1 200,00 €
   franchise de la formule confort : − 150,00 €   →   1 050,00 €
   montant estimé : 1 050,00 €
4. Anti-fraude — requis : F2 (contrat souscrit moins de 90 jours avant le sinistre).
   Avis indisponible : score hors de l'intervalle [0 ; 1] (couche « plausibilite »). Réponse non recopiée (§7, §9).
5. Décision — règle 6 du §10 : Remboursement accordé : 1 050,00 €. Décision prise sans avis anti-fraude, en mode dégradé (§9) : à contrôler.

Exécution : 5 étape(s) · borne atteinte : aucune · mode dégradé : oui
Revue de fond : aucune anomalie.
```

Version assuré, pour la même demande :

```
Votre demande KAL-26-0301
Issue : décision · ACCEPTÉE · 1 050,00 €

Montant (§6) — déclaré 1 200,00 € · justifié 1 200,00 € · retenu 1 200,00 €
   franchise de la formule confort : − 150,00 €   →   1 050,00 €
   montant estimé : 1 050,00 €
Motif : Remboursement accordé : 1 050,00 €.
```
