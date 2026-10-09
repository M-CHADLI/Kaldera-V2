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
| Photo(s) | `photo` | JPEG ou PNG | une pièce `photo` |
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

Choix par `KALDERA_EXTRACTION`. **L'extracteur par modèle envoie le texte du dossier, donnée personnelle comprise, au fournisseur du modèle** : c'est un choix explicite, jamais le défaut. Les identifiants Azure ne sont pas configurés aujourd'hui : cet extracteur est testé avec un faux modèle, **pas avec le vrai**.

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
