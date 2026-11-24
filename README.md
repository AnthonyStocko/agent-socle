# agent-socle

Briques techniques communes aux agents Savoye (issues d'`agent-scrum-master`, comportement inchangé) :
Jira, Bitbucket, Jenkins, base de données (lecture), Groundcover, MCP, masquage des secrets, `.env`, connexion OIDC,
mesure des jetons, connaissances partagées, mémoire des tickets, registre des livraisons, git de l'agent,
registre des projets en lecture (`projets` : façade sur les projets Cucumber et les applications du manager, client
de l'API d'agent-projets sur 8512 avec repli local), configuration commune transmise par le manager.
Aucune logique métier ; aucun import d'un agent.

| Installation | `pip install -e ..\agent-socle` (chantier) ou `agent-socle @ git+https://github.com/AnthonyStocko/agent-socle@v0.2.0` |
|---|---|
| Données | `AGENT_DATA_DIR` : dossier de `.tmp/` et `.env` ; défaut `..\agent-scrum-master` (`agent_socle.chemins`) |
| Tests | `python -m pytest -q` |
