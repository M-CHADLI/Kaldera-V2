# Journal des ajustements d'orchestration

Chaque entrée part d'un scénario rejoué et d'un signal observé, jamais d'un réglage au hasard. Règle suivie : une seule modification à la fois, puis les 28 scénarios rejoués ([4-plan-epreuve.md](conception/4-plan-epreuve.md)).

Résultats détaillés de la dernière épreuve : [epreuve-resultats.md](epreuve-resultats.md), produit par `uv run python scripts/epreuve.py --repetitions 3`.

| # | Date | Scénario | Signal observé | Cause | Ajustement | Preuve avant / après | Gardé ? |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-08 | NOM-05 | Demande refusée (0 €), alors que 3 000 € sont attendus | Le code fourni traite le plafond (§4) comme une condition d'éligibilité | **Frontière** : le plafond passe à l'Estimation, appliqué après la franchise, signalé, et la règle est rappelée dans le motif | NOM-05 échoue → passe | Oui |
| 2 | 2026-10-08 | BCL-01 | Fiche `en_attente` après 50 tours, `arret` vide | L'espace assuré re-soumet le même dépôt ; aucune borne propre à la boucle | **Borne** : `complements_max = 2` et arrêt sur dépôt identique (empreinte SHA-256) | 50 tours → 4 étapes, `arret = depot_identique` | Oui |
| 3 | 2026-10-08 | AF-01 à 07 | Requête refusée par le partenaire (`-32602`), données personnelles transmises | Toute la demande était envoyée | **Routage** : vue réduite de l'Anti-fraude et liste blanche des 7 champs dans l'adaptateur | 7 échecs → 7 réussites | Oui |
| 4 | 2026-10-08 | INV-01 à 07 | Réponses non conformes recopiées dans la fiche (dont `rembourser_integralement`) | Aucune validation des réponses | **Routage** : validation en 3 couches ; un rejet donne un avis indisponible, puis le mode dégradé | 5 échecs → 7 réussites | Oui |
| 5 | 2026-10-08 | PAN-02 | Demandes bloquées tant que le partenaire ne répond pas (`timeout=None`) | Pas de délai d'appel, lot traité en série | **Bornes** : abandon à 3 s pris sur le budget de la demande ; lot traité en parallèle | Lot de 3 : 3,07 s, contre au moins 15 s en série | Oui |
| 6 | 2026-10-08 | Les 28 | Étapes au plus : 7 (NOM-07, PAN-01) ; durée de lot au plus : 3,07 s | — | **Aucun** : `etapes_max = 12` et `duree_max_s = 8` gardent une marge suffisante. Pas de réduction tant que les 28 scénarios ne montrent pas de besoin. | 28/28 conformes et stables sur 3 rejeux | Bornes inchangées |
| 7 | 2026-10-08 | PAN-01 | 2 appels, 2 échecs : le disjoncteur ne s'est jamais ouvert | Les deux demandes concernées partent en parallèle, avant le premier échec | **Aucun pour l'instant** : `disjoncteur_echecs = 2` est sans effet sur un lot de cette taille. Limite consignée, à revoir si les lots grossissent. | — | Non ajusté |

## Ajustements écartés

| Idée | Pourquoi écartée |
|---|---|
| Un registre anti-doublon global au processus | Le banc d'acceptance réinitialise le partenaire entre les scénarios : un registre global refuserait des appels légitimes. Le registre est donc limité au lot. En production, il s'appuiera sur l'historique des demandes. |
