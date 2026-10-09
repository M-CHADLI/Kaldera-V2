# Cas de test de bout en bout

Quinze dossiers de pièces **fictifs** (noms, IBAN, adresses et e-mails en `example.org`
inventés) à importer dans la console, pour vérifier Kaldera de l'importation des pièces
jusqu'à la décision. Chaque cas existe en deux variantes qui racontent les mêmes faits.

| Variante | Documents | Extraction à choisir |
|---|---|---|
| `A-etiquete` | « Libellé : valeur », comme `exemples/pieces/` | `KALDERA_EXTRACTION=champs` (le défaut), sans modèle |
| `B-libre` | courrier de l'assuré, contrat en phrases, facture avec lignes et TVA, procès-verbal en phrases | `KALDERA_EXTRACTION=llm` (modèle gpt-5.4-mini) |

## Mode d'emploi

1. Lancer la console et un partenaire anti-fraude (voir le README du dépôt). Les résultats
   attendus ont été établis avec **notre partenaire** (`partenaire_antifraude/`) : le
   partenaire simulé a ses propres règles, ses avis peuvent différer.
2. Pour la variante B seulement, démarrer la console avec `KALDERA_EXTRACTION=llm` et les
   variables `AZURE_OPENAI_*` (le texte des documents part chez le fournisseur du modèle : ces
   dossiers sont fictifs, n'y importez pas de vraies pièces).
3. Dans la console, section « Pièces du dossier », importer les fichiers d'un dossier de cas
   (`01-degat-des-eaux-nominal/A-etiquete/`, par exemple) avec le bouton qui correspond à leur
   nom : `contrat` → « + Contrat », `declaration-sinistre` → « + Déclaration de sinistre »,
   `facture-…` → « + Facture(s) », `photo-…` → « + Photo(s) », `depot-de-plainte` →
   « + Dépôt de plainte ». Les numéros donnent l'ordre de dépôt.
4. Cliquer sur « Analyser le dossier », lire la fiche d'analyse, puis « Traiter la demande », et
   comparer l'issue au tableau ci-dessous (ou à `attendu.json`).

Chaque cas a sa propre référence `KAL-26-81NN`, écrite dans la déclaration. Un partenaire
n'évalue une référence qu'**une fois** : pour rejouer un cas qui consulte le partenaire
(04, 07, 11, 12, 13), redémarrez le partenaire, sans quoi le doublon (`-32029`) déclenche le
mode dégradé.

## Cas et résultats attendus

Résultats établis en **exécutant le vrai pipeline** (extraction de la variante A, puis
`kaldera.traiter_demande`, partenaire maison local), pas devinés. Détail dans `attendu.json`.

| Cas | Ce qu'il éprouve | Résultat attendu |
|---|---|---|
| `01-degat-des-eaux-nominal` (KAL-26-8101) | Le parcours complet sans accroc : formule confort, deux pièces exigées, aucun indicateur de risque, franchise déduite. | acceptée, 1 500,00 € |
| `02-plafond-essentiel` (KAL-26-8102) | Incendie à 4 400 € sous la formule essentiel : franchise de 300 €, puis plafond de 3 000 € atteint ; le motif doit le rappeler. | acceptée, 3 000,00 € (motif : « Plafond de la formule essentiel atteint ») |
| `03-vol-avec-plainte` (KAL-26-8103) | Vol sous la formule confort : facture et dépôt de plainte exigés (et non une photo), déclaration en 2 jours pour 5 autorisés, aucun indicateur de risque. | acceptée, 1 650,00 € |
| `04-fraude-elevee` (KAL-26-8104) | Vol de 7 200 € sur un contrat vieux de 82 jours, avec 3 sinistres sur 12 mois : le partenaire note 0,88 (élevé), escalade vers la cellule anti-fraude. | escalade `cellule_fraude` (avis `eleve`, 0,88) |
| `05-contrat-resilie` (KAL-26-8105) | Contrat résilié avant le sinistre : refus immédiat (E1), sans consulter le partenaire. | refusée, 0 € |
| `06-facture-illisible` (KAL-26-8106) | La facture est un PDF scanné, sans texte : pièce illisible, aucun dépôt de complément, escalade vers un gestionnaire (pièces manquantes). | escalade `gestionnaire` |
| `07-seuil-delegation` (KAL-26-8107) | Incendie de 12 000 € sous la formule premium (sans franchise) : le montant dépasse 10 000 €, escalade vers un gestionnaire après un avis de risque faible. | escalade `gestionnaire` (avis `faible`, 0,28) |
| `08-carence` (KAL-26-8108) | Sinistre 16 jours après la souscription : la carence de 30 jours s'applique, refus (E3). | refusée, 0 € |
| `09-declaration-hors-delai` (KAL-26-8109) | Vol déclaré 8 jours après les faits, pour 5 jours autorisés : refus (E4), alors que toutes les pièces sont fournies. | refusée, 0 € |
| `10-cotisations-impayees` (KAL-26-8110) | Contrat actif mais cotisations en retard : refus (E2). | refusée, 0 € |
| `11-risque-modere` (KAL-26-8111) | Dégât des eaux de 5 500 € sur un contrat de 60 jours : le partenaire note 0,46 (modéré), escalade vers un gestionnaire pour contrôle renforcé. | escalade `gestionnaire` (avis `modere`, 0,46) |
| `12-premium-deux-factures` (KAL-26-8112) | Incendie sous la formule premium : deux factures dont la somme (7 700 €) est remboursée sans franchise ; le montant dépasse 5 000 € donc le partenaire est consulté (faible). | acceptée, 7 700,00 € (avis `faible`, 0,28) |
| `13-bris-de-glace-ecart-declare` (KAL-26-8113) | Montant déclaré (1 100 €) supérieur de plus de 20 % à la facture (880 €) : le remboursement suit la facture, et l'indicateur F4 déclenche une consultation du partenaire (faible). | acceptée, 730,00 € (avis `faible`, 0,06) |
| `14-piece-manquante` (KAL-26-8114) | Dégât des eaux sans aucune photo : la pièce exigée manque et l'assuré n'a rien déposé, escalade vers un gestionnaire. | escalade `gestionnaire` |
| `15-garantie-non-couverte` (KAL-26-8115) | Vol sous la formule essentiel, qui ne couvre ni les vols ni les bris de glace : refus (E5), pièces complètes par ailleurs. | refusée, 0 € |

Le cas 06 contient une facture scannée : un PDF réduit à une image, sans couche de texte, donc
identique dans les deux variantes. Le cas 14 n'a pas de photo, volontairement.

## Régénérer et vérifier

```bash
uv run python scripts/generer_cas_exemples.py            # réécrit exemples/cas/ (reproductible)
uv run pytest -q -p no:cacheprovider tests/unit/test_cas_exemples.py
```

Le test traite la variante A de chaque cas et compare à `attendu.json`, sans réseau ni modèle : le
partenaire est remplacé par un faux qui applique sa règle de score (0,06 de base, +0,22 si montant
≥ 5 000 €, +0,18 si ancienneté < 90 jours, +0,30 si ≥ 3 sinistres sur 12 mois, +0,12 pour un vol ;
faible < 0,40 ≤ modéré < 0,75 ≤ élevé). Il vérifie aussi que les dossiers B ont des PDF lisibles, aucune
ligne « Libellé : valeur » et les mêmes pièces que les dossiers A.

Pour **rétablir `attendu.json`** après un changement de règles, avec le vrai pipeline (le partenaire
refuse un second avis pour une même référence : le redémarrer avant chaque passe) :

```bash
PARTENAIRE_JETON=jeton-de-cas uv run uvicorn partenaire_antifraude.app:app --port 8211
PARTENAIRE_JETON=jeton-de-cas PARTENAIRE_URL=http://127.0.0.1:8211 \
    uv run python scripts/generer_cas_exemples.py --attendu
```

## Résultat réel de la variante B avec le vrai modèle

Mesures du 9 octobre 2026 avec gpt-5.4-mini (Azure OpenAI), `KALDERA_EXTRACTION=llm`, sur ces seuls
documents fictifs. Le contrat et la déclaration passent chacun par le modèle (deux appels par cas) ; les
factures, photos et dépôts de plainte sont lus sans modèle.

**Résultat final : 15 cas B sur 15 donnent la même demande que la variante A** (identité, référence,
formule, statut, cotisations, dates, type de sinistre, montant déclaré, historique, code postal, pièces),
prête à traiter. La décision attendue est donc celle de la variante A ; elle n'a pas été rejouée dans ce
test, seule la demande extraite est comparée.

Durée de l'extraction d'un cas : 2,5 à 8 s, avec **deux valeurs isolées à 64 et 68 s** (cas 04 et 06) :
un appel au modèle a dépassé son délai de 60 s puis a été relancé une fois. Une extraction peut donc être
longue ; la console affiche « Analyse en cours… » pendant ce temps.

### Ce que la première mesure a révélé

La première passe, avant correction, donnait **0 cas sur 15** : tous « À COMPLÉTER ». Les défauts, trouvés
par cet essai et corrigés dans `src/kaldera/extraction.py` :

| Défaut | Effet | Correction |
|---|---|---|
| Le gabarit de la consigne contenait `"montant_declare": 0.0` ; le modèle le recopiait pour le contrat, et la première valeur trouvée l'emportait sur le vrai montant de la déclaration | Montant déclaré vide, 15 cas bloqués | Gabarit entièrement à `null` ; un montant nul ou négatif n'est jamais retenu |
| Une entrée de pièce vide dans le gabarit, recopiée à chaque document | « type de pièce inconnu » dans 3 cas sur 4 | `"pieces": []` ; une pièce sans type est ignorée |
| « Aucun sinistre » non compris comme 0 | `historique.sinistres_12_mois` illisible | Nombres écrits en lettres reconnus |
| Le contrat renvoyait son numéro à la place de la référence du dossier | Référence générée au lieu de `KAL-26-81xx` (12 cas sur 15) | Seule une référence au format `KAL-AA-NNNN` est retenue |
| Total de facture sans « : » (« Total TTC 1 650,00 € ») non lu | Facture comptée pour 0 €, donc **refus** | Total lu avec ou sans « : » ; une facture dont le montant reste illisible devient une pièce illisible, donc une escalade, jamais un refus |

### Écarts relevés à la première passe, sans effet sur la décision

La comparaison finale (15 sur 15) ne porte ni sur la description ni sur l'adresse complète ; ces écarts
n'ont pas été rejoués après correction et peuvent subsister :

- `sinistre.description` est reformulée par le modèle (même sens, autre texte).
- `assure.adresse` est parfois donnée sans code postal ni ville ; le code postal, lui, est extrait à part.
- Une pièce citée dans un courrier mais non importée (par exemple une plainte annoncée) est conservée
  comme pièce illisible d'après le texte (cas 10). Importée, elle prévaut ; non importée, elle peut
  déclencher une escalade « pièces manquantes ».

Ces écarts viennent du modèle : une nouvelle passe peut en produire d'autres. La mesure ci-dessus est
une passe, pas une garantie de stabilité.
