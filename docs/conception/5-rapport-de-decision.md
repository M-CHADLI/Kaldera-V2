# + · Le rapport de décision

[← Sommaire](README.md)

## Pourquoi

La fiche de décision ([§11](../specs_metier.md#L196-L209)) donne l'issue et un motif d'une ligne. Ça ne suffit pas pour un gestionnaire qui reprend un dossier, pour un assuré qui conteste, ni pour un contrôle a posteriori du mode dégradé. **Chaque demande produit donc un rapport qui motive et explique sa décision**, étape par étape, en citant la règle appliquée.

## Ce qu'il contient

| Partie | Contenu | Auteur de l'information |
|---|---|---|
| Issue | Décision ou escalade, montant, file, motif, mode dégradé | Superviseur-décideur |
| Éligibilité | Résultat, et la condition du §4 qui a échoué s'il y en a une | Éligibilité |
| Pièces | Pièces reçues, compléments demandés, dépôts lus | Pièces |
| Montant | Le calcul complet : déclaré, justifié, retenu, franchise, **plafond s'il s'applique, avec le rappel de la règle** | Estimation |
| Anti-fraude | Indicateurs F1 à F4 relevés, statut de l'avis, couche de validation qui a échoué le cas échéant | Anti-fraude |
| Règle du §10 | Le numéro de la règle qui a fixé l'issue | Superviseur-décideur |
| Exécution | Étapes consommées, borne atteinte le cas échéant | Superviseur |

## Comment il est produit

- **De façon déterministe**, à partir de l'état et de la trace, avec un gabarit par partie. Chaque phrase cite sa source (une section de la spec, une étape de la trace).
- **Le LLM est facultatif** : s'il est configuré, il reformule en langage clair, **sans changer les faits**. Un contrôle vérifie que tous les montants et tous les numéros de règle du texte reformulé figurent dans l'état. Si ce contrôle échoue, le gabarit est conservé.
- **Le LLM ne reçoit jamais** la réponse brute du partenaire, la description libre ni les données personnelles. Il reçoit seulement les valeurs déjà validées.
- **Deux versions** :
  - **gestionnaire** : le rapport complet ;
  - **assuré** : l'issue, le motif et le calcul du montant, **sans le détail du contrôle anti-fraude**, qui est une information sensible.

Le rapport est ajouté à la fiche dans un champ `rapport`, et conservé dans l'historique après neutralisation des données personnelles.

## Exemple 1 · le plafond appliqué (NOM-05)

```
Rapport de décision · KAL-26-0105
Issue : décision · ACCEPTÉE · 3 000,00 €

1. Éligibilité — éligible : les 5 conditions du §4 sont remplies.
2. Pièces — complètes : facture lisible (4 200,00 €), photo lisible.
3. Montant (§6, §4)
   déclaré 4 200,00 € · justifié 4 200,00 € · retenu 4 200,00 €
   franchise de la formule essentiel : − 300,00 €   →   3 900,00 €
   PLAFOND APPLIQUÉ : la formule essentiel rembourse au plus 3 000,00 € par sinistre
   « Aucune demande ne peut donner lieu à un remboursement supérieur au plafond
     de sa formule. » (§4)
   montant estimé : 3 000,00 €
4. Anti-fraude — non requis : aucun indicateur F1 à F4.
5. Décision — règle 6 du §10 : acceptée au montant estimé.
Exécution : 5 étapes · aucune borne atteinte · mode dégradé : non
```

## Exemple 2 · le mode dégradé (INV-01)

```
Rapport de décision · KAL-26-0301
Issue : décision · ACCEPTÉE · 1 050,00 € · MODE DÉGRADÉ

3. Montant — déclaré 1 200,00 € · justifié 1 200,00 € · franchise confort − 150,00 €
   montant estimé : 1 050,00 €
4. Anti-fraude — requis : F2 (contrat souscrit 63 jours avant le sinistre, moins de 90).
   Partenaire consulté une fois. Réponse rejetée à la couche 3 (plausibilité) :
   score hors de l'intervalle [0 ; 1]. Avis indisponible, réponse non recopiée.
5. Décision — mode dégradé (§9) : montant estimé ≤ 1 500 €, la demande continue.
   Règle 6 du §10 : acceptée. Contrôle a posteriori recommandé.
```
