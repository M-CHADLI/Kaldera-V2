# Contrat d'échange — Service anti-fraude partenaire

*Version 2.0 — en vigueur depuis le 1er septembre 2026. Remplace la version 1.4.*

Le partenaire met à disposition de Kaldera un agent d'évaluation du risque de
fraude, interrogeable selon le protocole agent-à-agent (A2A) : découverte par
*Agent Card*, échanges en JSON-RPC 2.0 sur HTTP. L'agent émet un **avis
consultatif** ; la décision sur la demande reste de la responsabilité de
l'assureur.

## Changements par rapport à la version 1.4

- Schéma de requête **strict** : tout champ non listé ci-dessous est refusé.
- **Minimisation des données** : plus aucune donnée d'identité, de coordonnées
  ou bancaire n'est acceptée. L'ancienneté du contrat et le département
  remplacent la date de souscription et l'adresse.
- **Plus aucune relance** : un seul appel par dossier ; les doublons sont refusés
  et signalés.
- Délai de réponse garanti abaissé à 2 secondes.

## 1. Accès

| Élément | Valeur |
|---|---|
| Découverte | `GET /.well-known/agent.json` (Agent Card) |
| Point d'appel | `POST /a2a` — JSON-RPC 2.0, méthode `message/send` |
| Authentification | en-tête `Authorization: Bearer <jeton>` (jeton fourni par le partenaire) |
| Format | `application/json`, UTF-8 |

## 2. Requête

### Enveloppe

```json
{
  "jsonrpc": "2.0",
  "id": "c0a8012e-4f1b-4c55-9d1e-2b7e1f0e6a10",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "messageId": "8d3f2a64-1c0e-4e2b-a7b5-0f6c9e1d2a33",
      "parts": [
        {
          "kind": "data",
          "data": {
            "reference_dossier": "KAL-26-0042",
            "type_sinistre": "degat_des_eaux",
            "montant_declare": 1850.0,
            "date_survenance": "2026-08-14",
            "anciennete_contrat_jours": 942,
            "sinistres_12_mois": 0,
            "departement": "69"
          }
        }
      ]
    }
  }
}
```

Le message contient **exactement une** partie de type `data`.

### Données autorisées

Tous les champs sont obligatoires. **Aucun autre champ n'est accepté.**

| Champ | Type | Contrainte |
|---|---|---|
| `reference_dossier` | chaîne | référence Kaldera du dossier, forme `KAL-AA-NNNN` |
| `type_sinistre` | chaîne | `degat_des_eaux`, `incendie`, `bris_de_glace` ou `vol` |
| `montant_declare` | nombre | strictement positif, en euros |
| `date_survenance` | chaîne | date `AAAA-MM-JJ` |
| `anciennete_contrat_jours` | entier | ≥ 0 — jours entre souscription et survenance |
| `sinistres_12_mois` | entier | ≥ 0 |
| `departement` | chaîne | 2 premiers caractères du code postal (`2A`/`2B` pour la Corse, 3 chiffres pour l'outre-mer) |

### Données interdites

Ne doivent **jamais** être transmises, sous quelque forme que ce soit (champ
dédié, champ texte, valeur détournée) :

- l'identité et les coordonnées de l'assuré (nom, prénom, e-mail, téléphone,
  adresse, code postal complet) ;
- les données bancaires (IBAN) ;
- les identifiants internes de l'assureur (identifiant client, numéro de
  contrat) ;
- la description libre du sinistre ;
- les pièces justificatives et leur contenu.

## 3. Réponse

### Enveloppe

En cas de succès, le partenaire renvoie une tâche terminée portant un artefact
`data` :

```json
{
  "jsonrpc": "2.0",
  "id": "c0a8012e-4f1b-4c55-9d1e-2b7e1f0e6a10",
  "result": {
    "kind": "task",
    "id": "tsk-5d0c1b9e",
    "status": {"state": "completed"},
    "artifacts": [
      {
        "artifactId": "art-5d0c1b9e",
        "parts": [
          {
            "kind": "data",
            "data": {
              "reference_dossier": "KAL-26-0042",
              "score": 0.08,
              "niveau": "faible",
              "indicateurs": [],
              "evaluation_id": "EVA-3f9a1c2b7d",
              "version_modele": "af-2.3.1"
            }
          }
        ]
      }
    ]
  }
}
```

### Évaluation

| Champ | Type | Contrainte |
|---|---|---|
| `reference_dossier` | chaîne | identique à celle de la requête |
| `score` | nombre | entre 0 et 1 inclus |
| `niveau` | chaîne | `faible`, `modere` ou `eleve` |
| `indicateurs` | liste de chaînes | valeurs parmi `MONTANT_ELEVE`, `SINISTRE_PRECOCE`, `FREQUENCE_ELEVEE`, `TYPE_SENSIBLE` |
| `evaluation_id` | chaîne | identifiant de l'évaluation, à conserver pour audit |
| `version_modele` | chaîne | version du modèle d'évaluation |

### Cohérence

- `niveau` est `faible` si `score` < 0,40 ; `modere` si 0,40 ≤ `score` < 0,75 ;
  `eleve` si `score` ≥ 0,75.
- La réponse ne comporte aucun champ en dehors de ceux listés ci-dessus.
- L'`id` JSON-RPC de la réponse est celui de la requête.

Une réponse qui ne respecte pas l'une de ces règles **n'engage pas le
partenaire** : elle doit être écartée par le client, jamais exploitée.

## 4. Erreurs

| Situation | Réponse |
|---|---|
| Jeton absent ou invalide | HTTP 401 |
| Service indisponible | HTTP 503 |
| Corps illisible | JSON-RPC `-32700` |
| Enveloppe invalide | JSON-RPC `-32600` |
| Méthode inconnue | JSON-RPC `-32601` |
| Données non conformes (champ inconnu, absent ou invalide) | JSON-RPC `-32602`, détail dans `error.data` |
| Dossier déjà évalué | JSON-RPC `-32029` |

## 5. Délais

- Le partenaire s'engage à répondre en **2 secondes** au plus.
- Le client abandonne l'appel **au plus tard 3 secondes** après l'envoi. Un
  avis non reçu dans ce délai est réputé indisponible.

## 6. Limites d'appel

- **Un seul appel par dossier** (`reference_dossier`).
- **Aucune relance automatique** : ni après un délai dépassé, ni après une
  erreur, ni après une réponse écartée.
- Tout appel en doublon est refusé (`-32029`) et signalé à l'assureur comme
  manquement au contrat.
