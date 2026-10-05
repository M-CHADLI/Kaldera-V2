

Pour chaque agent
Délimiter ce qu'il peut, ce qu'il ne doit surtout pas faire
Le contrat
Que reçoit et que renvoie chaque agent ?
Quels gardes fou doit contenir chaque agent ?
Les outils sont ils paratgés ?

Quelles étapes dépendent les unes des autres, et lesquelles peuvent s'exécuter en parallèle ?

 Comment l'orchestrateur garantit-il que chaque demande se termine par une décision ou une escalade humaine motivée ?
 
 Observabilité (à préparer dès maintenant)
Quelles métriques par agent ?
Comment montrer qu'une demande a suivi le bon chemin ?

Spécifications : contrat A2A et mode dégradé / Spec: A2A contract and fallback mode
a. Quel est le contrat d'échange avec le partenaire anti-fraude ?
b. Quelles données ont le droit de partir chez le partenaire, et comment le filtre garantit-il que rien d'autre ne sort ?
« Quel est le point ambigu entre deux agents, et qui en est le seul responsable ? »

Comment se partagent ils l'etat / memoire

Un seul agent avec 10 à 15 outils au maximum suffit-il ?
Les étapes sont elles connues d'avance, dans quel ordre s'enchainent elles ?
Est-ce que les sous tâches sont connues à l'avance et sont elles indépendantes ?
Un seul spécialiste suffit-il pour chaque requête ?
Faut il un contrôle central et traçable ?
Comment vérifier automatiquement et rapidement que les specs sont bien respectées ?
Comment vérifier les boucles (condition de sortie, nombre de tours max, Done, artifact de sortie) ?
Quels éléments sont observés au niveau de l'équipe et son orchestration ?
Quelle gestion d'erreur observable mettre en place dans le workflow ?
Sous quelle former la mémoire partagée doit elle être implémentée ?


Qui decide : code, boucle, un superviseur ou  les agents verifient en eux ?
Pour rappel : code : arret facile à garantir, previsibler, peu flexible LLM ; flexible mais difficile à garantir...


