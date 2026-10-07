# Spécifications fonctionnelles — Traitement des demandes de remboursement

*Kaldera Assurances — Direction des opérations · version 3.2 · septembre 2026*

## 1. Objet

Ce document décrit le traitement automatisé d'une demande de remboursement
d'assurance habitation : les contrôles à mener, les règles chiffrées qui les
gouvernent, les cas d'escalade vers un gestionnaire et le fonctionnement attendu
lorsque le service anti-fraude du partenaire est indisponible.

Il fait référence pour le comportement attendu de la plateforme. Le contrat
d'échange avec le partenaire anti-fraude est décrit séparément
(`external_agent/contrat.md`).

## 2. Parcours d'une demande

Une demande déposée par un assuré passe par les contrôles suivants :

1. **Contrôle d'éligibilité** — le contrat couvre-t-il ce sinistre (section 4) ?
2. **Contrôle des pièces justificatives** — le dossier contient-il les pièces
   exigées, lisibles et cohérentes (section 5) ?
3. **Estimation du montant** — combien l'assureur rembourse-t-il (section 6) ?
4. **Contrôle anti-fraude** — uniquement lorsque la demande présente un
   indicateur de risque ; l'avis est demandé au partenaire (section 7).
5. **Issue** — la demande reçoit une décision (acceptée ou refusée) ou est
   escaladée vers une file de traitement humain (sections 8 à 10).

Une demande est **traitée** lorsqu'elle a reçu une issue. Il n'existe pas
d'autre état final : une demande ne reste jamais « en attente » sans qu'un
humain en ait été saisi.

### Séparation des responsabilités

Chaque contrôle a un responsable unique et ne déborde pas sur les autres :

- le contrôle d'éligibilité ne chiffre pas la demande ;
- l'estimation ne se prononce pas sur la fraude ;
- l'avis de fraude est émis par le partenaire, jamais en interne ;
- seule la décision conclut la demande.

Chaque contrôle réalisé doit être imputable à son responsable (traçabilité).

## 3. Données d'une demande

Une demande est transmise au format JSON :

| Champ | Description |
|---|---|
| `reference` | Référence du dossier, de la forme `KAL-AA-NNNN` |
| `assure` | Identité et coordonnées : `id_client`, `nom`, `prenom`, `email`, `telephone`, `iban`, `adresse`, `code_postal` |
| `contrat` | `numero`, `formule` (`essentiel`, `confort`, `premium`), `date_souscription`, `statut` (`actif`, `suspendu`, `resilie`), `cotisations_a_jour` (booléen) |
| `sinistre` | `type` (`degat_des_eaux`, `incendie`, `bris_de_glace`, `vol`), `date_survenance`, `date_declaration`, `montant_declare` (€), `description` (texte libre saisi par l'assuré) |
| `pieces` | Pièces jointes au dépôt : `type` (`facture`, `photo`, `depot_plainte`), `lisible` (booléen), `montant` (€, factures uniquement) |
| `historique` | `sinistres_12_mois` : nombre de sinistres déclarés par l'assuré sur les 12 derniers mois |
| `espace_assure` | Dépôts effectués par l'assuré dans son espace en ligne, dans l'ordre, en réponse aux demandes de complément |

Les dates sont au format `AAAA-MM-JJ`. L'**ancienneté du contrat** est le nombre
de jours entre la date de souscription et la date de survenance du sinistre.

## 4. Éligibilité

### Formules

| Formule | Garanties couvertes | Franchise | Plafond par sinistre |
|---|---|---|---|
| `essentiel` | dégât des eaux, incendie | 300 € | 3 000 € |
| `confort` | dégât des eaux, incendie, bris de glace, vol | 150 € | 8 000 € |
| `premium` | dégât des eaux, incendie, bris de glace, vol | 0 € | 20 000 € |

### Règles

Une demande est éligible si et seulement si toutes les conditions suivantes sont
remplies :

- **E1 — Contrat actif** : le contrat est au statut `actif`.
- **E2 — Cotisations** : les cotisations sont à jour.
- **E3 — Carence** : le sinistre est survenu au moins **30 jours** après la
  souscription.
- **E4 — Délai de déclaration** : le sinistre a été déclaré au plus tard
  **30 jours** après sa survenance (**5 jours** pour un vol).
- **E5 — Garantie** : le type de sinistre fait partie des garanties de la formule.

**Plafond de garantie.** Chaque formule fixe un plafond par sinistre (tableau
ci-dessus). Aucune demande ne peut donner lieu à un remboursement supérieur au
plafond de sa formule.

Une demande non éligible est refusée, quel que soit l'état de ses pièces ; le
motif cite la ou les conditions non remplies.

## 5. Pièces justificatives

| Type de sinistre | Pièces exigées |
|---|---|
| dégât des eaux | facture, photo |
| incendie | facture, photo |
| bris de glace | facture, photo |
| vol | facture, dépôt de plainte |

Le contrôle des pièces vérifie leur présence, leur lisibilité et leur cohérence
avec la déclaration.

Toute pièce exigée absente ou illisible fait l'objet d'une **demande de
complément** adressée à l'assuré via son espace en ligne. Le contrôle reprend
dès que l'assuré a déposé une nouvelle pièce.

Si l'assuré n'a déposé aucune pièce du type demandé, la demande est escaladée
vers un gestionnaire (motif : pièces manquantes).

## 6. Estimation du montant

- Le **montant justifié** est la somme des montants des factures lisibles.
- Le **montant retenu** est le plus petit des deux montants : montant déclaré,
  montant justifié. L'assureur ne rembourse jamais plus que ce qui est déclaré.
- Le **montant estimé** est le montant retenu diminué de la franchise de la
  formule, sans pouvoir être négatif.

Les montants sont exprimés en euros, arrondis au centime.

## 7. Contrôle anti-fraude

### Indicateurs de risque

Le contrôle anti-fraude est requis dès qu'**au moins un** des indicateurs suivants
est présent :

- **F1** — montant déclaré supérieur ou égal à **5 000 €** ;
- **F2** — ancienneté du contrat inférieure à **90 jours** ;
- **F3** — au moins **3 sinistres** déclarés sur les 12 derniers mois ;
- **F4** — montant déclaré supérieur de plus de **20 %** au montant justifié.

### Avis du partenaire

Le contrôle consiste à obtenir l'avis du service anti-fraude du partenaire,
selon son contrat d'échange. L'avis comporte un niveau de risque :

| Niveau | Conséquence |
|---|---|
| `faible` | la demande suit son cours |
| `modere` | escalade vers un gestionnaire (contrôle renforcé) |
| `eleve` | escalade vers la cellule anti-fraude |

L'avis du partenaire est consultatif : il n'est utilisé que s'il est conforme à
son contrat d'échange. Une réponse non conforme n'est jamais utilisée, ni
recopiée dans le dossier.

## 8. Seuils d'escalade

| Situation | File humaine | Motif |
|---|---|---|
| Montant estimé supérieur à **10 000 €** | `gestionnaire` | seuil de délégation dépassé |
| Avis anti-fraude `modere` | `gestionnaire` | contrôle renforcé |
| Avis anti-fraude `eleve` | `cellule_fraude` | suspicion de fraude |
| Pièces manquantes (aucun dépôt de l'assuré) | `gestionnaire` | pièces manquantes |
| Avis anti-fraude indisponible, montant estimé supérieur à 1 500 € | `cellule_fraude` | contrôle anti-fraude manuel (section 9) |

Toute escalade précise la file destinataire et un motif lisible par le
gestionnaire qui reprend le dossier.

## 9. Mode dégradé — partenaire anti-fraude indisponible

Le partenaire est considéré comme **indisponible** pour une demande lorsque son
avis n'a pas pu être obtenu : absence de réponse dans le délai prévu par le
contrat, erreur du service, ou réponse non conforme au contrat.

Dans ce cas, et uniquement pour les demandes qui requièrent un contrôle
anti-fraude :

- **montant estimé inférieur ou égal à 1 500 €** : la demande continue sans avis
  anti-fraude et reçoit sa décision selon les autres règles ; la décision est
  marquée comme prise en mode dégradé, pour contrôle a posteriori ;
- **montant estimé supérieur à 1 500 €** : la demande est escaladée vers la
  cellule anti-fraude (`cellule_fraude`) pour un contrôle manuel, et marquée
  comme traitée en mode dégradé.

Les demandes qui ne requièrent pas de contrôle anti-fraude ne sont pas
affectées par l'indisponibilité du partenaire. Aucune demande n'attend le retour
du partenaire au-delà du délai prévu par son contrat.

## 10. Règles de décision

Les règles s'appliquent dans l'ordre ; la première qui s'applique fixe l'issue.

1. Demande non éligible → **refusée** (montant remboursé : 0 €).
2. Pièces manquantes → **escalade** `gestionnaire`.
3. Montant estimé nul (dommage inférieur ou égal à la franchise) → **refusée**
   (montant remboursé : 0 €).
4. Contrôle anti-fraude requis :
   - avis `modere` → **escalade** `gestionnaire` ;
   - avis `eleve` → **escalade** `cellule_fraude` ;
   - avis indisponible → mode dégradé (section 9) ;
   - avis `faible` → la demande poursuit.
5. Montant estimé supérieur à 10 000 € → **escalade** `gestionnaire`.
6. Sinon → **acceptée**, le montant remboursé étant le montant estimé.

## 11. Fiche de décision

Toute demande traitée produit une fiche de décision :

| Champ | Description |
|---|---|
| `reference` | Référence du dossier |
| `issue` | `decision` ou `escalade` |
| `decision` | `acceptee` ou `refusee` ; `null` en cas d'escalade |
| `montant_rembourse` | Montant accordé (0 en cas de refus) ; `null` en cas d'escalade |
| `motif` | Motif de l'issue, rédigé pour l'assuré ou le gestionnaire (obligatoire) |
| `file` | File humaine destinataire (`gestionnaire`, `cellule_fraude`) en cas d'escalade ; `null` sinon |
| `avis_fraude` | Avis anti-fraude retenu (`niveau`, `score`) ; `null` si aucun avis n'a été requis ou exploitable |
| `mode_degrade` | `true` si la demande a été traitée selon le mode dégradé (section 9) |

## 12. Engagements de service

- Toute demande reçoit une issue en **10 secondes** au plus de traitement
  automatisé.
- Une demande ne reste jamais sans issue, y compris lorsque le partenaire est
  lent, indisponible ou répond de manière non conforme.
- Le traitement d'une demande n'est jamais retardé par celui d'une autre.
- Les données transmises au partenaire se limitent à celles prévues par son
  contrat d'échange.
