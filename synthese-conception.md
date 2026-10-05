# Kaldera V2 : synthèse des questions de conception

Les questions de la promo (`question-promo.md`) sont ici comparées au brief, partie « Travail préliminaire de conception ».

## 1. Regroupement des questions de la promo

Les questions sont rangées selon les 4 blocs du dossier de conception. Les doublons ont été fusionnés.

### A. Carte des agents (exigence 2)

- Rôle de chaque agent : ce qu'il peut faire, ce qu'il ne doit pas faire, ses gardes-fous
- Contrat interne : ce que chaque agent reçoit et renvoie
- Outils partagés ou propres à chaque agent
- Point ambigu entre deux agents, et qui en est le seul responsable
- Dépendances entre étapes et parallélisme
- Justifier le multi-agent : un agent avec 10 à 15 outils suffit-il ? un seul spécialiste par requête suffit-il ?

### B. Orchestration & mémoire partagée (exigences 1 et 6)

- Étapes connues d'avance ou non, ordre fixe ou non : workflow codé ou agent planificateur
- Qui décide : le code, une boucle, un superviseur, ou les agents se vérifient eux-mêmes
- Contrôle central traçable
- Terminaison garantie : toujours une décision ou une escalade
- Boucles : condition de sortie, nombre de tours max, Done, artefact de sortie
- Forme de la mémoire partagée et façon de la partager

### C. A2A & mode dégradé (exigences 3, 4, 5)

- Contrat d'échange avec le partenaire anti-fraude
- Données autorisées à sortir, et comment le filtre le garantit

#### C.1 Le protocole A2A : cinq objets

Le contrat d'échange repose sur cinq objets :

- **Agent Card** : la carte d'identité de l'agent. Elle dit qui il est, ce qu'il sait faire (ses *skills*) et comment s'authentifier. Elle est publiée à l'adresse `/.well-known/agent-card.json`.
- **Task** : l'unité de travail. Elle a un identifiant et un état. Plusieurs tâches d'une même conversation partagent un `contextId`.
- **Message** : un tour de parole entre le client et l'agent. Il est découpé en Parts.
- **Part** : un morceau de contenu. Elle porte du texte, un fichier ou des données JSON.
- **Artifact** : le résultat de la tâche, lui aussi fait de Parts.

**Appliqué à Kaldera**

1. L'Agent Card du partenaire annonce un skill « évaluer le risque de fraude ».
2. L'agent fraude de Kaldera envoie un message avec une seule Part de données JSON : les champs du contrat, rien d'autre.
3. Ce message crée une tâche chez le partenaire. Elle passe à l'état `working`, puis `completed` ou un état d'échec.
4. À la fin, l'artifact contient le verdict anti-fraude, en JSON.

```text
Agent fraude Kaldera                          Partenaire anti-fraude
        │                                               │
        │── 1. lit l'Agent Card ───────────────────────▶│  skill « évaluer le risque »
        │── 2. Message (Part JSON : champs filtrés) ───▶│
        │                                               │  3. Task : submitted → working
        │◀─ 4. Task completed + Artifact (verdict) ─────│
        │                                               │
   5. validation de la réponse (C.4)
```

**Le contrat, c'est ce sur quoi les deux côtés sont d'accord : si un champ manque, l'échange échoue.** Chez Kaldera, c'est vrai dans les deux sens :

- si notre requête est incomplète ou contient un champ en trop, le partenaire la refuse ;
- si sa réponse est incomplète ou contient un champ en trop, nous la rejetons (exigence 4).

Le protocole fixe l'enveloppe : ces cinq objets. Le contrat du partenaire fixe le contenu : les champs de la Part JSON (voir C.2).

**Le reste du protocole utile pour la conception**

| Élément | Ce qu'on en fait chez Kaldera |
|---|---|
| **États de tâche** : `submitted`, `working`, `input-required`, `completed`, `failed`, `canceled`, `rejected`, `auth-required`, `unknown` | Chaque état doit mener à une réaction définie (voir C.5) |
| **`contextId`** | Rattacher toutes les tâches d'une même demande, par exemple après un retry |
| **Modes d'interaction** : synchrone (`message/send`), streaming (`message/stream`), notification par webhook (push) | Choisir un seul mode et le justifier ; le synchrone avec timeout est le plus simple à borner |
| **Suivi** : `tasks/get` (lire l'état), `tasks/cancel` (annuler) | `tasks/cancel` quand le délai est dépassé, pour ne pas laisser de tâche orpheline |
| **Erreurs** : JSON-RPC 2.0 (ex. `-32602` paramètres invalides) + erreurs A2A (ex. `-32001` tâche introuvable) | Les classer en rejouables et non rejouables (voir C.2) |
| **Transport et sécurité** : JSON-RPC 2.0 sur HTTPS, authentification déclarée dans l'Agent Card | Les identifiants passent dans les en-têtes HTTP, jamais dans le message |

Les noms de méthodes varient selon la version du protocole : se caler sur la version déclarée dans l'Agent Card du partenaire.

#### C.2 Le contrat : ce qu'il faut écrire noir sur blanc

| Rubrique | Ce qu'il faut définir |
|---|---|
| **Requête** | Liste fermée des champs, avec type, format et caractère obligatoire. Identifiant de demande pseudonymisé plutôt que les vraies références client |
| **Réponse** | Schéma attendu : identifiant de corrélation, verdict (liste fermée de valeurs), score (bornes), code motif |
| **Délais** | Timeout par appel et budget total pour l'étape anti-fraude |
| **Retries** | Erreurs rejouables (réseau, HTTP 503) ou non (réponse invalide, `-32602`). Nombre maximum, délai croissant entre les essais, respect de l'en-tête `Retry-After` |
| **Doublons** | Que faire si un retry crée une deuxième tâche chez le partenaire ? Le partenaire dédoublonne-t-il sur le `messageId` ? |
| **Version** | Version du contrat dans le schéma, pour détecter un changement côté partenaire |

Exemple **fictif** de requête (les vrais champs viendront du contrat du partenaire) :

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "messageId": "msg-7f3a",
      "parts": [{
        "kind": "data",
        "data": {
          "claim_ref": "CLM-PSEUDO-8842",
          "claim_type": "auto",
          "amount_claimed": 4200.00,
          "incident_date": "2026-09-12"
        }
      }]
    }
  }
}
```

Exemple **fictif** de réponse :

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "kind": "task",
    "id": "task-123",
    "status": { "state": "completed" },
    "artifacts": [{
      "artifactId": "art-1",
      "parts": [{
        "kind": "data",
        "data": {
          "claim_ref": "CLM-PSEUDO-8842",
          "risk_level": "high",
          "score": 0.82,
          "reason_code": "R12"
        }
      }]
    }]
  }
}
```

#### C.3 Le filtre des données sortantes (exigence 3)

- **Construire, ne pas nettoyer** : on crée un objet neuf qui ne contient que les champs du contrat. On ne part pas de la demande complète pour en retirer des champs, car un champ ajouté plus tard passerait le filtre.
- **Valider avant l'envoi** : le message sortant est vérifié contre le schéma du contrat, sans champ supplémentaire autorisé (`additionalProperties: false`). En cas d'échec, rien ne part.
- **Un seul point de sortie** : seul l'agent fraude parle au partenaire, et seulement à travers ce filtre.
- **Logs** : journaliser ce qui est parti sans recopier les données sensibles dans les traces.
- **Preuve** : un test glisse des données sensibles dans la mémoire de la demande et vérifie qu'elles n'apparaissent pas dans le message envoyé.

#### C.4 La validation des réponses (exigence 4)

| Niveau | Ce qu'on vérifie |
|---|---|
| **Protocole** | JSON-RPC valide, `id` identique à celui de la requête, état de tâche connu |
| **Schéma** | Présence d'une `data` part conforme au contrat, sans champ en trop, avec les bons types |
| **Sens** | `claim_ref` identique à celui envoyé, score dans ses bornes, verdict cohérent avec le score, code motif connu |

- Une réponse qui échoue à un seul niveau est rejetée et journalisée. Elle n'entre jamais dans la mémoire partagée.
- Seuls les champs structurés validés sont gardés. Un texte libre du partenaire n'est jamais injecté dans le prompt d'un autre agent (risque d'injection).

#### C.5 Chaque situation doit avoir une réaction

Les réactions sont des propositions à confronter à `specs_metier.md`.

| Situation | Ce qu'on observe | Réaction proposée |
|---|---|---|
| Cas nominal | `completed` + artefact valide | Verdict écrit dans la mémoire, la demande continue |
| Partenaire lent | Toujours `working` au-delà du timeout | `tasks/cancel`, puis mode dégradé |
| Partenaire en panne | Erreur réseau, HTTP 5xx, pas de réponse | Retries bornés, puis mode dégradé |
| Réponse invalide | Échec protocole ou schéma | Rejet sans retry, puis mode dégradé ou escalade (à trancher) |
| Partenaire « menteur » | Schéma OK, sens incohérent | Rejet et journalisation, puis même suite que la réponse invalide |
| Refus | `rejected` ou `failed` | À trancher : mode dégradé ou escalade |
| Demande d'informations | `input-required` | Ne rien envoyer hors contrat : annuler, puis escalade |
| Problème d'accès | `auth-required` ou HTTP 401/403 | Pas de retry, alerte technique, mode dégradé |
| Réponse tardive | Arrive après le passage en mode dégradé | Ignorée ou journalisée (à trancher), sans changer la décision déjà prise |

### D. Observabilité & plan d'épreuve (exigence 6)

- Métriques par agent et pour l'équipe
- Prouver qu'une demande a suivi le bon chemin
- Gestion d'erreur observable
- Vérification automatique du respect des specs

## 2. Couverture des exigences du brief

| Exigence | Couverte ? |
|---|---|
| 1. Décision ou escalade **motivée** | ⚠️ La terminaison est couverte, le « motivée » ne l'est pas |
| 2. Rôles et frontières | ✅ Bien couverte |
| 3. Seules les données prévues sortent | ✅ Couverte |
| 4. Réponse non conforme rejetée | ❌ Aucune question |
| 5. Mode dégradé | ❌ Seulement le titre, aucune question |
| 6. Pas de boucle infinie + métriques + journal | ⚠️ Rien sur le journal des ajustements |
| Livrable « plan d'épreuve » | ❌ Presque absent |

## 3. Angles morts à travailler

### Avant tout

- [ ] Récupérer `specs_metier.md` et `eval/scenarios.jsonl` : le mode dégradé et le plan d'épreuve en dépendent.

### Carte des agents

- [ ] Liste précise des agents : qui rend la décision finale et qui rédige le motif ?
- [ ] Qui déclenche la « suspicion de fraude » ? Bon candidat pour le point ambigu : face à un montant aberrant ou une pièce douteuse, est-ce un signal de fraude ou une anomalie d'estimation ou de pièces ?
- [ ] Règles de décision quand les agents ne sont pas d'accord (ex. éligible mais pièces incomplètes).

### Orchestration

- [ ] Bornes provisoires : quelles valeurs de départ (tours, timeouts, budget de tokens) ?
- [ ] Escalade motivée : que contient le dossier d'escalade (motif normalisé, étapes faites, preuves) et à qui va-t-il ?
- [ ] Que faire quand un agent **interne** plante ou renvoie un format invalide ?

### Mémoire partagée

- [ ] Accès maîtrisé : qui lit et écrit quels champs ? L'estimation doit-elle voir le score de fraude ?
- [ ] Écritures simultanées quand des agents tournent en parallèle.
- [ ] Reprise après un crash, pour ne pas recréer des demandes bloquées.

### A2A

- [ ] Validation des réponses à trois niveaux : protocole, schéma, sens (voir C.4). Un partenaire « menteur » peut renvoyer le bon format avec un contenu incohérent.
- [ ] Une réponse rejetée compte-t-elle comme une indisponibilité (mode dégradé) ou mène-t-elle à une escalade ?
- [ ] Définir « indisponible » : timeout, erreur ou lenteur ? Avec quel délai ?
- [ ] « Pas de retry sauvage » : combien de nouvelles tentatives, quel délai entre elles, faut-il un circuit breaker ?
- [ ] Une réponse qui arrive après le passage en mode dégradé : on l'ignore, on la journalise, on rouvre la demande ?
- [ ] Filtre en liste blanche ou en liste noire ? Et les logs ne doivent pas eux-mêmes laisser fuiter les données.
- [ ] Choisir le mode d'interaction (synchrone, streaming ou push) et vérifier la version du protocole dans l'Agent Card (voir C.1).
- [ ] Trancher les réactions marquées « à trancher » dans le tableau C.5, en particulier `input-required` : le partenaire demande des données hors contrat.
- [ ] Doublons : un retry peut-il créer deux tâches chez le partenaire ?

### Plan d'épreuve

- [ ] Construire le tableau scénario × signal observé × ajustement du chantier 1. Exemple : partenaire lent → la latence de l'agent fraude monte → on ajuste le timeout.
- [ ] Scénarios minimum : cas nominal, panne, partenaire lent, réponse invalide, partenaire menteur, piège à boucle.
- [ ] Comment simuler le partenaire (un mock réglable) ?
- [ ] Format du journal des ajustements : scénario, signal, changement, avant/après.
- [ ] Les LLM ne répondent pas toujours pareil : combien de rejeux faut-il pour qu'un test soit probant ?

### Hors brief, mais réels

- [ ] Injection de prompt cachée dans les pièces justificatives envoyées par le client.
- [ ] Les demandes déjà bloquées depuis des semaines : faut-il les reprendre ? (question à poser au formateur)

## 4. À retenir

- La question « qui décide : code ou LLM ? » commande presque toutes les autres. Les exigences 1, 4 et 6 sont des garanties absolues (« jamais », « aucune »), qu'un LLM ne peut pas garantir. D'où le découpage courant : l'orchestration, les bornes et la validation A2A en code, le LLM seulement dans les agents spécialistes.
- Le brief parle de bornes « provisoires » et exige un journal des ajustements. Le formateur attend donc des valeurs ajustées par les scénarios rejoués, pas fixées au doigt mouillé. Le plan d'épreuve est la partie la moins préparée, alors que c'est celle qui sera la plus questionnée.
