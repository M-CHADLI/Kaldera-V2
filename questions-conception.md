# Kaldera V2 : les questions à trancher

Ce document liste les questions auxquelles le dossier de conception doit répondre. Il reprend les questions de la promo (`question-promo.md`) et ajoute les angles morts repérés en les comparant au brief. Le détail des explications est dans `synthese-conception.md`.

**Comment l'utiliser**

- Écrire la réponse de l'équipe sous chaque question, puis cocher la case.
- `[E1]` à `[E6]` renvoient aux exigences de la direction des opérations (tableau ci-dessous).
- 🔍 signale un angle mort : une question absente de la liste de la promo.

| | Exigence de la direction des opérations |
|---|---|
| E1 | Toute demande se termine par une décision ou une escalade humaine motivée |
| E2 | Chaque agent a un rôle et une frontière ; aucun n'empiète sur un autre |
| E3 | Seules les données prévues au contrat partent chez le partenaire |
| E4 | Une réponse du partenaire non conforme au contrat est rejetée |
| E5 | Partenaire indisponible → le mode dégradé défini par le métier s'applique |
| E6 | Aucune boucle infinie ; métriques par agent visibles ; ajustements consignés |

## 0. Avant de commencer

- [ ] 🔍 Avons-nous `specs_metier.md` et `eval/scenarios.jsonl` ? Que disent-ils du mode dégradé et des scénarios à rejouer ?
- [ ] 🔍 Quels tests d'acceptance sont fournis, et que vérifient-ils exactement ?

## 1. Le choix d'architecture

- [ ] Un seul agent avec 10 à 15 outils au maximum suffirait-il ? Si non, pourquoi ? [E2]
- [ ] Les étapes sont-elles connues d'avance ? Dans quel ordre s'enchaînent-elles ?
- [ ] Les sous-tâches sont-elles connues d'avance, et sont-elles indépendantes ?
- [ ] Un seul spécialiste suffit-il pour chaque demande, ou faut-il en combiner plusieurs ?
- [ ] Faut-il un contrôle central et traçable ? [E1]
- [ ] Qui décide de la suite : le code, une boucle, un superviseur, ou les agents se vérifient-ils eux-mêmes ? [E1] [E6]
  - Rappel : le code est prévisible et facile à arrêter, mais peu flexible. Un LLM est flexible, mais difficile à garantir.
- [ ] 🔍 Quelles exigences sont des garanties absolues (« jamais », « aucune ») et doivent donc reposer sur du code plutôt que sur un LLM ?

## 2. La carte des agents [E2]

- [ ] 🔍 Quels sont exactement les agents ? Éligibilité, pièces, estimation, fraude… et qui d'autre ?
- [ ] Pour chaque agent : que peut-il faire, et que ne doit-il surtout pas faire ?
- [ ] Que reçoit et que renvoie chaque agent ?
- [ ] Quels gardes-fous chaque agent doit-il contenir ?
- [ ] Les outils sont-ils partagés entre agents, ou chacun a-t-il les siens ?
- [ ] Quel est le point ambigu entre deux agents, et qui en est le seul responsable ?
  - 🔍 Piste : face à un montant aberrant ou une pièce douteuse, est-ce un signal de fraude, ou une anomalie d'estimation ou de pièces ?
- [ ] 🔍 Qui déclenche la « suspicion de fraude » qui mène à l'appel du partenaire ?
- [ ] 🔍 Qui rend la décision finale, et qui rédige le motif ?
- [ ] 🔍 Que décide-t-on quand les agents ne sont pas d'accord ? Par exemple : éligible, mais pièces incomplètes.
- [ ] 🔍 Comment prouver par un test qu'un agent ne sort pas de son rôle ?

## 3. L'orchestration [E1] [E6]

- [ ] Quelles étapes dépendent les unes des autres, et lesquelles peuvent s'exécuter en parallèle ?
- [ ] Comment l'orchestrateur garantit-il que chaque demande se termine par une décision ou une escalade humaine motivée ?
- [ ] Comment borne-t-on les boucles : condition de sortie, nombre de tours max, état Done, artefact de sortie ?
- [ ] 🔍 Quelles bornes provisoires au départ (tours, timeouts, budget de tokens ou de coût) ? Sur quelle base les choisit-on ?
- [ ] 🔍 Qu'est-ce qu'une escalade « motivée » ? Quel motif, quelles étapes déjà faites, quelles preuves, et à qui l'envoie-t-on ?
- [ ] 🔍 Que se passe-t-il quand un agent **interne** plante ou renvoie un format invalide ?
- [ ] Quelle gestion d'erreur observable met-on en place dans le workflow ?

## 4. La mémoire partagée

- [ ] Comment les agents partagent-ils l'état de la demande ?
- [ ] Sous quelle forme la mémoire partagée doit-elle être implémentée ?
- [ ] 🔍 « Accès maîtrisé » : qui lit et qui écrit quels champs ? L'estimation doit-elle voir le score de fraude ?
- [ ] 🔍 Que se passe-t-il si deux agents qui tournent en parallèle écrivent en même temps ?
- [ ] 🔍 Peut-on reprendre une demande après un crash, sans la bloquer à nouveau ?
- [ ] 🔍 Quels champs de la mémoire ne doivent jamais partir chez le partenaire ? [E3]

## 5. La collaboration A2A [E3] [E4]

Rappel : l'échange A2A repose sur cinq objets. L'**Agent Card** est la carte d'identité du partenaire. La **Task** est l'unité de travail. Le **Message** est un tour de parole, découpé en **Parts** (texte, fichier ou JSON). L'**Artifact** est le résultat de la tâche.

### Le protocole

- [ ] 🔍 Que contient l'Agent Card du partenaire : quel skill, quelle version du protocole, quelle authentification ?
- [ ] 🔍 Vérifie-t-on l'Agent Card au démarrage ? Que fait-on si le skill ou la version attendus manquent ?
- [ ] 🔍 Quel mode d'échange choisit-on : synchrone, streaming ou notification (push) ? Pourquoi ?
- [ ] 🔍 Comment relie-t-on une tâche A2A à sa demande Kaldera ? Garde-t-on le `contextId` et le `taskId` dans la mémoire ?

### Le contrat

- [ ] Quel est le contrat d'échange avec le partenaire anti-fraude ?
- [ ] 🔍 Quels champs exactement dans la requête ? Avec quel type, quel format, obligatoires ou non ?
- [ ] 🔍 Envoie-t-on les vraies références client, ou un identifiant pseudonymisé ?
- [ ] 🔍 Quel schéma attend-on en réponse : identifiant de demande, verdict, score, code motif ?
- [ ] 🔍 Comment repère-t-on que le partenaire a changé la version de son contrat ?

### Le filtre des données sortantes [E3]

- [ ] Quelles données ont le droit de partir chez le partenaire, et comment le filtre garantit-il que rien d'autre ne sort ?
- [ ] 🔍 Liste blanche (on construit un objet neuf) ou liste noire (on retire des champs) ? Que se passe-t-il quand un nouveau champ est ajouté plus tard à la demande ?
- [ ] 🔍 Valide-t-on le message sortant contre le schéma du contrat avant de l'envoyer ?
- [ ] 🔍 Un seul agent a-t-il le droit de parler au partenaire ?
- [ ] 🔍 Nos logs et nos traces laissent-ils fuiter des données qu'on n'a pas le droit d'envoyer ?

### La validation des réponses [E4]

- [ ] 🔍 Qu'est-ce qu'une réponse « non conforme » ?
  - Au niveau du protocole : JSON-RPC invalide, identifiant de requête différent, état de tâche inconnu ?
  - Au niveau du schéma : champs manquants, champs en trop, mauvais types ?
  - Au niveau du sens : mauvais identifiant de demande, score hors bornes, verdict incohérent avec le score ?
- [ ] 🔍 Comment repère-t-on un partenaire « menteur », qui répond au bon format avec un contenu faux ?
- [ ] 🔍 Une réponse rejetée mène-t-elle au mode dégradé ou à une escalade ?
- [ ] 🔍 Garde-t-on le texte libre du partenaire ? Si oui, comment éviter qu'il injecte des instructions dans le prompt d'un autre agent ?

## 6. Le mode dégradé [E5]

- [ ] 🔍 Que dit `specs_metier.md` : la demande continue, ou elle est routée ? Si elle est routée, vers qui ?
- [ ] 🔍 À partir de quand le partenaire est-il « indisponible » : timeout, erreur, lenteur ? Avec quel délai ?
- [ ] 🔍 « Pas de retry sauvage » : quelles erreurs rejoue-t-on, combien de fois, avec quel délai entre deux essais ?
- [ ] 🔍 Faut-il un circuit breaker pour arrêter d'appeler un partenaire en panne ?
- [ ] 🔍 Un retry peut-il créer deux tâches chez le partenaire ?
- [ ] 🔍 Annule-t-on la tâche chez le partenaire (`tasks/cancel`) quand on passe en mode dégradé ?
- [ ] 🔍 Que fait-on d'une réponse qui arrive après le passage en mode dégradé ?
- [ ] 🔍 Quelle réaction pour chaque état d'échec A2A : `failed`, `rejected`, `auth-required`, `input-required` ?
  - Attention : `input-required` veut dire que le partenaire réclame plus de données. Que fait-on, sachant que rien ne doit sortir hors contrat ?

## 7. L'observabilité [E6]

- [ ] Quelles métriques par agent ?
  - 🔍 Le brief en impose trois : la latence, les échecs et le recours à l'externe. Comment mesure-t-on chacune ?
- [ ] Quels éléments observe-t-on au niveau de l'équipe et de son orchestration ?
- [ ] Comment montrer qu'une demande a suivi le bon chemin ?
- [ ] 🔍 Où ces métriques sont-elles « visibles » : tableau de bord, logs, rapport ?

## 8. Le plan d'épreuve [E6]

- [ ] Comment vérifier automatiquement et rapidement que les specs sont respectées ?
- [ ] Comment prouver que le scénario piège à boucle s'arrête bien dans les bornes ?
- [ ] 🔍 Quels scénarios rejoue-t-on au minimum ? Cas nominal, panne, partenaire lent, réponse invalide, partenaire menteur, piège à boucle… et quoi d'autre ?
- [ ] 🔍 Pour chaque scénario : quel signal observe-t-on, et quel ajustement du chantier 1 peut-il déclencher ?
- [ ] 🔍 Comment simule-t-on le partenaire : un mock qu'on peut régler (lent, en panne, menteur) ?
- [ ] 🔍 Quel format pour le journal des ajustements : scénario, signal, changement, valeur avant et après ?
- [ ] 🔍 Les LLM ne répondent pas toujours pareil : combien de rejeux faut-il pour qu'un résultat soit probant ?

Tableau à remplir en équipe :

| Scénario | Signal observé | Ajustement possible du chantier 1 |
|---|---|---|
| Cas nominal | | |
| Partenaire en panne | | |
| Partenaire lent | | |
| Réponse invalide | | |
| Partenaire menteur | | |
| Piège à boucle | | |

## 9. Hors brief, mais réels

- [ ] 🔍 Une pièce justificative envoyée par le client peut-elle contenir une injection de prompt ? Comment s'en protège-t-on ?

## 10. À poser au formateur

- [ ] Où trouver `specs_metier.md`, `eval/scenarios.jsonl` et les tests d'acceptance ?
- [ ] Le contrat réel du partenaire est-il fourni (schéma, délais, règles de retry) ?
- [ ] Les demandes déjà bloquées depuis des semaines font-elles partie du périmètre ?
