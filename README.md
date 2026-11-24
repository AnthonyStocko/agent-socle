# agent-socle

Briques techniques communes aux agents Savoye (issues d'`agent-scrum-master`, comportement inchangé) :
Jira, Bitbucket, Jenkins, base de données (lecture), Groundcover, MCP, masquage des secrets, `.env`, connexion OIDC,
mesure des jetons, connaissances partagées, mémoire des tickets, registre des livraisons, git de l'agent.
Aucune logique métier ; aucun import d'un agent.

| Installation | `pip install -e ..\agent-socle` (chantier) ou `agent-socle @ git+https://github.com/AnthonyStocko/agent-socle@v0.1.0` |
|---|---|
| Données | `AGENT_DATA_DIR` : dossier de `.tmp/` et `.env` ; défaut `..\agent-scrum-master` (`agent_socle.chemins`) |
| Tests | `python -m pytest -q` |
