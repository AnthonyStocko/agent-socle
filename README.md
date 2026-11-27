# agent-socle

Briques techniques communes aux agents Savoye (issues d'`agent-scrum-master`, comportement inchangé) :
Jira, Bitbucket, Jenkins, base de données (lecture), Groundcover (et sa configuration dans l'IHM : `ihm_groundcover`), MCP, masquage des secrets, `.env`, connexion OIDC,
mesure des jetons, connaissances partagées, mémoire des tickets, registre des livraisons, git de l'agent,
registre des projets en lecture (`projets` : façade sur les projets Cucumber et les applications du manager, client
de l'API d'agent-projets sur 8512 avec repli local), configuration commune transmise par le manager.
Aucune logique métier ; aucun import d'un agent.

| Installation | `pip install -e ..\agent-socle` (chantier) ou `agent-socle @ git+https://github.com/AnthonyStocko/agent-socle@v0.2.0` |
|---|---|
| Données | `AGENT_DATA_DIR` : dossier de `.tmp/` et `.env` (`C:\agent-data`) ; défaut `..\agent-data` (`agent_socle.chemins`) |
| Tests | `python -m pytest -q` |

<!-- Section reprise du README d'agent-scrum-master (supprimé) : le .env partagé d'AGENT_DATA_DIR et agent_socle.knowledge_tools sont communs à tous les agents. -->

## Connaissances partagées

Chaque analyse des agents est déposée en Markdown dans un répertoire commun (partage réseau d'entreprise), puis consultée avant les analyses suivantes, par vous comme par vos collègues. C'est un complément de la mémoire locale (`.tmp/memory`, propre à chaque poste), qui reste inchangée. Le code est dans `agent_socle/knowledge_tools.py` ; le masquage des secrets, commun à tous les agents, dans `agent_socle/secret_tools.py`.

### Configuration

| Variable | Rôle |
|---|---|
| `AGENT_KNOWLEDGE_DIR` | Répertoire partagé : chemin UNC (`\\serveur\partage\dossier`), lecteur mappé (`X:\dossier`) ou chemin POSIX (`/mnt/partage/dossier`). **Vide = fonction désactivée** : rien n'est déposé ni consulté. |
| `AGENT_KNOWLEDGE_AUTHOR` | Auteur inscrit dans les documents (vide = utilisateur système). |
| `AGENT_KNOWLEDGE_MAX_CONTEXT` | Taille maximale, en caractères, des connaissances injectées dans un prompt (défaut 6000, 0 = aucune). |

Dans le manager, onglet **Configuration › Réglages des agents**, section « Connaissances partagées », enregistrez le chemin, puis dans agent-projets (Projets et connexions) cliquez sur **Tester le répertoire partagé** : existence du dossier, lecture, droit d'écriture (un fichier témoin est créé, relu puis supprimé) et temps d'accès. Chaque opération est bornée à 15 s ; un échec dit quoi vérifier (chemin, réseau ou VPN, droits).

### Arborescence et format

```
<AGENT_KNOWLEDGE_DIR>/<projet>/<type>/<AAAA-MM-JJ_HHMMSS>_<sujet>_<auteur>.md
```

- `<projet>` : le client s'il est connu (déduit du dépôt client), sinon le projet Jira. Le projet Jira figure toujours dans l'en-tête.
- `<type>`, liste fermée : `cadrage`, `besoin`, `decoupage-epopee`, `recap-patch`, `release-note`, `postmerge-cucumber`, `cucumber-inventaire`, `cucumber-sante`, `cucumber-couverture`, `cucumber-a-revoir`, `cucumber-diagnostic-run`, `cucumber-initialisation` (constats et mises de côté de l'initialisation), `cucumber-reponses` (réponses aux questions du profil), `cucumber-livraison` (bilan de la livraison autonome), `audit`, `autre`.
- Noms nettoyés pour Windows (caractères interdits, noms réservés, points finaux), chemin complet borné à 240 caractères.
- Un document n'est **jamais écrasé** : à nom identique, un suffixe `-2`, `-3`… est ajouté. L'écriture est atomique (fichier temporaire dans le même dossier, puis renommage) : un lecteur ne voit jamais un document à moitié écrit.

Chaque document commence par un en-tête YAML (une valeur JSON par ligne), suivi du corps de l'analyse tel quel :

```yaml
---
projet: "PROJ"
client: "<client>"
type: "cadrage"
sujet: "Titre du ticket"
tickets: ["PROJ-123"]
composants: ["<composant>"]
tags: []
date: "2026-10-26T09:05:07"
auteur: "<auteur>"
version_agent: "<git describe du dépôt de l'agent>"
depots: [{"nom": "<dépôt>", "commit": "<sha>"}]
statut: "actif"
remplace_par: ""
sources_partagees: ["<client>/cadrage/<document consulté>.md"]
resume: "5 lignes au plus"
---
```

`statut` vaut `actif`, `obsolète` ou `remplacé` (avec `remplace_par`, chemin relatif du document qui le remplace).

### Dépôt automatique

L'agent dépose, à la fin de chaque étape réussie :

| Étape | Type |
|---|---|
| Cadrage, révision, cadrage complété par les réponses | `cadrage` |
| Rédaction du besoin | `besoin` |
| Découpage d'une épopée (avec l'analyse de chaque tâche) | `decoupage-epopee` |
| Patch : récapitulatif de l'agent, release note | `recap-patch`, `release-note` |
| Post-merge Cucumber | `postmerge-cucumber` |
| Cucumber : inventaire (`--inventory-only`), bilan de santé, couverture (un document par génération), `A_REVOIR.md`, import d'un run | `cucumber-inventaire`, `cucumber-sante`, `cucumber-couverture`, `cucumber-a-revoir`, `cucumber-diagnostic-run` |

- **Nouvelle version** : un document de même projet, même type et même ticket (sans ticket : même sujet) marque automatiquement l'ancienne version active « remplacée par » la nouvelle, **quel qu'en soit l'auteur**. Un document déposé en retard ne remplace jamais une version plus récente.
- **Partage indisponible** : l'analyse n'est jamais bloquée. Le document (déjà masqué) attend dans la file locale `.tmp/knowledge_outbox`, réessayée au démarrage de chaque étape, avant chaque dépôt et depuis l'onglet Connaissances partagées du manager (bouton **Déposer les documents en attente**).
- **Import ponctuel** de `.md` existants (`A_REVOIR.md`, `AUDIT.md`, `COUVERTURE.md`…) : onglet Connaissances partagées du manager, panneau « Importer des analyses Markdown existantes », ou en ligne de commande :

```powershell
venv\Scripts\python.exe -m agent_socle.knowledge_tools import A_REVOIR.md --projet PROJ --type cucumber-a-revoir --tickets PROJ-1 --client <client>
venv\Scripts\python.exe -m agent_socle.knowledge_tools flush   # dépose la file locale
```

### Consultation avant analyse

- Avant chaque analyse, l'agent cherche les documents pertinents : **même projet d'abord**, puis tickets, composants, tags et mots-clés communs (même similarité que la mémoire locale). Un document d'un autre projet n'est retenu que s'il a un point commun ; les documents obsolètes ou remplacés sont exclus.
- L'index est reconstruit à partir des en-têtes et mis en cache sur le poste (`.tmp/knowledge_index.json`) : seul un dossier `<projet>/<type>` modifié depuis la dernière lecture est relu. **Aucun fichier d'index n'est écrit sur le partage.** Partage injoignable : le dernier index connu est utilisé.
- Les plus proches puis les plus récents sont injectés dans le prompt (variable `${knowledge_block}`), dans la limite de `AGENT_KNOWLEDGE_MAX_CONTEXT` : chemin, date, auteur, statut, résumé et sections utiles (diagnostic et fichiers d'un cadrage, sinon début du document).
- Le bloc est présenté comme une **CONNAISSANCE ANTÉRIEURE À VÉRIFIER** : des données, jamais des instructions. Aucune consigne trouvée dans un document partagé ne s'applique ; le code et les résultats d'exécution l'emportent toujours sur un document.
- L'agent peut lire les documents complets (`--add-dir`), avec écriture et modification interdites sur ce répertoire (`--disallowedTools`) et la consigne de lecture seule. Les lots Cucumber ne reçoivent que les extraits.
- Les documents consultés sont affichés dans la console et listés dans le document déposé (en-tête `sources_partagees` et section finale « Connaissances partagées consultées »).

### Confidentialité

- **Tout utilisateur qui a accès au partage lit tous les documents**, de tous les projets et de tous les clients. Réglez les droits du partage en conséquence (un partage par périmètre de confidentialité si nécessaire) et ne le configurez pas sur un poste qui ne doit pas voir ces analyses.
- Avant tout dépôt, les secrets sont masqués avec les mêmes règles que le reste de l'agent : mots de passe et jetons (`-Dpassword*`, `-DuserName`, `-D*token*`, paramètres d'URL et champs JSON), en-têtes `Authorization`, formes base64 de ces valeurs, et valeurs secrètes de votre `.env` (`*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `*_API_KEY`).
- **Si un motif de secret subsiste après masquage** (clé privée, jeton JWT, Atlassian, GitHub, Anthropic, clé AWS…), le dépôt est **refusé** : rien n'est écrit, ni sur le partage ni dans la file locale, et la console l'indique.
- Le masquage n'est pas une garantie absolue : ne collez pas de données personnelles ou de secrets dans les tickets et les analyses.

### Bonnes pratiques

- Testez le répertoire après chaque changement de configuration ; un accès lent (plus de 2 s) ralentit chaque dépôt et chaque consultation.
- Marquez **obsolète** (onglet Connaissances partagées du manager) un document devenu faux, plutôt que de le supprimer : il reste consultable sur demande et n'est plus injecté.
- Ne modifiez pas le corps d'un document à la main : déposez une nouvelle analyse, qui remplacera l'ancienne. Une retouche manuelle de l'en-tête reste lisible (valeurs JSON ou texte simple).
- Ne créez pas d'autres fichiers dans les dossiers `<projet>/<type>` : seuls les `.md` sont indexés, les fichiers commençant par `.` sont ignorés.
- Une information tirée d'un document partagé se vérifie dans le code avant d'être reprise.
