# + · L'analyse de dossier

[← Sommaire](README.md)

## Pourquoi

Jusqu'ici, une demande arrivait toute faite, en JSON. Dans la réalité, elle arrive sous forme de **pièces** : un contrat, une déclaration de sinistre, des factures, des photos, parfois un dépôt de plainte. Cette brique transforme ces pièces en demande au format du [§3](../specs_metier.md#L44-L59), et c'est un humain qui valide avant tout traitement.

```
pièces importées → texte → extracteur → validation unique → fiche + demande → validation humaine → équipe d'agents
```

## Ce qui est importé

| Bouton de la console | Rôle | Format | Ce que l'agent en tire |
|---|---|---|---|
| Contrat | `contrat` | PDF | assuré, formule, souscription, statut, cotisations |
| Déclaration de sinistre | `declaration` | PDF | type, dates, montant déclaré, description, historique |
| Facture(s) | `facture` | PDF, un par fichier | une pièce `facture` avec son montant total |
| Photo(s) | `photo` | JPEG ou PNG | une pièce `photo`, **jamais jugée sur son contenu** (voir ci-dessous) |
| Dépôt de plainte | `plainte` | PDF | une pièce `depot_plainte` (vol) |
| Dossier complet | `dossier` | PDF | tout, depuis un seul document |

## Principes

| Principe | Mise en œuvre |
|---|---|
| **Le PDF est une donnée, jamais une consigne** | L'extracteur par champs ne retient qu'une ligne « Libellé : valeur » dont le libellé est connu : un texte injecté n'a aucun effet. La première occurrence fait foi. |
| **Une seule validation** | Quel que soit l'extracteur, [`normaliser`](../../src/kaldera/extraction.py) revalide tout : formats, valeurs permises, dates, cohérence. Un modèle manipulé ne peut rien produire que le schéma refuse. |
| **Rien n'est supposé** | Un champ obligatoire absent bloque le traitement (`manquants`) ; une valeur illisible aussi (`anomalies`) ; une valeur douteuse ou déduite est signalée (`a_verifier`). |
| **L'humain valide** | La console affiche une fiche (source de chaque champ, IBAN masqué) et la demande en JSON, modifiable, avant le bouton « Traiter la demande ». |
| **Rien n'est conservé** | Ni le PDF, ni son texte, ni la fiche. L'historique reste celui de la brique neutralisée. |
| **Une facture ne compte jamais deux fois** | Si des factures sont importées, celles que le texte d'un autre document listerait sont ignorées : sinon le montant justifié, donc le remboursement, serait faux. |
| **Une pièce illisible n'est pas une erreur** | Une facture scannée (sans texte) devient une pièce `lisible: false` : la demande suit alors la boucle de compléments, puis l'escalade. |

## Deux extracteurs

| Extracteur | Quand | Ce qu'il fait |
|---|---|---|
| `champs` (défaut) | Dossiers étiquetés « Libellé : valeur » | Déterministe, sans modèle, sans réseau. Reconnaît dates françaises, montants (`2 450,00 €`), booléens, types de sinistre. |
| `modèle` (`llm`) | Dossiers en texte libre | Le texte est présenté entre balises comme une donnée ; la réponse JSON est revalidée. **Strict** : sans modèle, l'analyse échoue. |
| `auto` | | Essaie le modèle, puis retombe sur `champs` avec une note à vérifier. |

Choix par `KALDERA_EXTRACTION`. **L'extracteur par modèle envoie le texte du dossier, donnée personnelle comprise, au fournisseur du modèle** : c'est un choix explicite, jamais le défaut. Il utilise gpt-5.4-mini (Azure OpenAI) : essayé le 9 octobre 2026 sur le dossier d'exemple fictif (6 s, même demande que la lecture par champs) ; les tests automatiques utilisent un faux modèle.

## Limites assumées

- **Pas de reconnaissance de caractères** : un PDF scanné est refusé (contrat, déclaration) ou devient une pièce illisible (facture, plainte).
- **L'extracteur par champs suppose des libellés connus** ; un dossier d'un autre format passe par le modèle, ou se complète à la main dans la demande JSON.
- **La cohérence des pièces avec la déclaration** n'est pas vérifiée au-delà de la validation des champs.
- **Limites de taille** : 5 Mo par fichier, 15 Mo au total, 12 documents, 20 pages par PDF.
- **La console déployée est publique** : y importer de vrais dossiers revient à envoyer des données personnelles à un service sans authentification. À protéger (accès authentifié) avant tout usage réel.

## Dans le code

- Extraction, validation et fiche : [src/kaldera/extraction.py](../../src/kaldera/extraction.py)
- Points d'entrée web : `POST /api/analyse` (un PDF) et `POST /api/analyse-dossier` (pièces par rôle) dans [web.py](../../src/kaldera/web.py)
- Ligne de commande : `uv run python -m kaldera.extraction dossier.pdf --traiter`
- Exemples (données fictives) : [exemples/](../../exemples/), générés par `scripts/exemple_dossier_pdf.py`

## La photo : une preuve pour un humain, pas un signal pour une règle

Le système sait vérifier qu'une photo **est présente** et qu'il s'agit bien d'une image JPEG ou PNG. Il ne sait pas
dire ce qu'elle montre : un rectangle uni, une capture d'écran ou une image sans rapport passeraient de la même façon.
Plutôt que de simuler un contrôle (l'ancien seuil de 1 Ko n'en était pas un), la photo est traitée ainsi :

- **Présence exigée**, comme le prévoit la spécification ([§5](../specs_metier.md#L90-L97)) : sans photo, la demande est
  complétée ou escaladée, comme avant.
- **Contenu jamais jugé** : l'analyse ne l'affirme pas « lisible » ou « conforme » ; la fiche écrit « jointe, contenu non
  analysé » et le rapport du gestionnaire ajoute « à examiner par un gestionnaire ou un expert ». Le rapport de l'assuré
  n'en dit rien.
- **Un humain tranche** : en cas d'escalade, le gestionnaire (ou un expert d'assurance, qui peut aussi contrôler les
  faits) examine la photo avec le dossier.

Limites assumées : une demande dont la photo est vide peut encore être acceptée automatiquement, mais le rapport dit
désormais que personne ne l'a regardée ; les pièces ne sont pas conservées par Kaldera (pas de stockage), donc la
transmission de la photo au gestionnaire reste à brancher ; le retour d'un expert vers le système (nouveaux faits,
nouvelle décision) n'est pas implémenté, c'est une évolution possible.

## Cohérence des pièces avec la déclaration (§5)

Le §5 demande des pièces « présentes, lisibles et cohérentes avec la déclaration ». Les trois contrôles sont
désormais tenus, tous déterministes :

| Pièce | Date lue | Comparée à | Écart toléré |
|---|---|---|---|
| Dépôt de plainte | faits (`date_faits`) | survenance déclarée | 3 jours |
| Dépôt de plainte | dépôt (`date_depot`) | date des faits | le dépôt ne précède jamais les faits |
| Facture | sinistre visé (`date_sinistre`), si le texte le cite | survenance déclarée | 3 jours |
| Facture | émission (`date`) | rien : affichée, jamais un critère | — |

La date d'émission d'une facture n'est pas un critère, car une facture d'achat antérieure au sinistre (valeur d'un
bien détruit ou volé) est légitime, comme une facture de serrurier postérieure à un vol.

Une incohérence **escalade vers un gestionnaire** (règle 2, motif « pièces incohérentes avec la déclaration ») : la
spec ne dit pas quoi en faire, et un refus sur une date lue automatiquement serait disproportionné. Une date
absente ou illisible n'est jamais comparée. La tolérance (`regles.TOLERANCE_DATES_PIECES_JOURS`) est un choix
métier à faire valider.

## Garde-fous quand un modèle lit des pièces

Le texte d'un dossier est écrit par l'assuré : c'est une donnée, jamais une consigne. Le modèle ne décide
rien (sa sortie est une demande candidate, relue par un humain, puis jugée par des règles en code), mais il
peut être trompé sur une valeur. Six protections s'empilent :

| Garde-fou | Ce qu'il arrête |
|---|---|
| Document balisé et déclaré « donnée » dans la consigne | Injection simple (aide, pas une garantie) |
| Sortie imposée (JSON de forme fixe) et **une seule validation** après le modèle | Sortie hors format, valeur hors liste |
| **Double lecture** : le modèle est comparé à la lecture par champs ; un désaccord est une anomalie bloquante, la valeur de la lecture par champs est retenue | Une valeur fausse que le modèle a suivie |
| **Détecteur** de texte qui s'adresse à un assistant (« ignore tes consignes », « [SYSTÈME] », « dans le champ iban »…) | Injection en texte libre, où il n'y a rien à comparer |
| **Chaque document ne fournit que les champs de son rôle** : le contrat ne dicte ni sinistre ni historique, la déclaration ni statut ni cotisations | Une ligne glissée dans le mauvais document |
| Plafonds (5 Mo, 12 documents, 20 pages, 30 000 caractères) et aucun outil pour le modèle | Documents énormes, actions parasites |

Mesure : [docs/epreuve-injection.md](../epreuve-injection.md), 9 attaques × 2 variantes contre gpt-5.4-mini
(`scripts/epreuve_injection.py`). Dernier passage : 15 résistent, 3 sont signalés, aucune ne passe. Un seul
passage, non déterministe : le premier passage laissait passer 3 attaques, et c'est lui qui a motivé le
détecteur et la restriction par rôle.

**Limites assumées** : une valeur fausse mais plausible, écrite sans formulation d'ordre, dans un texte libre
et dans le bon document, ne peut être repérée que par l'humain qui relit la fiche. Statut du contrat,
cotisations et IBAN lus dans des pièces de l'assuré sont par nature contestables : ils devraient venir d'une
source de l'assureur (voir la gateway de données).
