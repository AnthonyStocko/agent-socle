"""
Composant Streamlit commun : configuration Groundcover d'un agent (extrait d'app.py d'agent-scrum-master, comportement
inchangé), à placer dans le formulaire de configuration de l'agent appelant.

- champs_acces_api() : accès à l'API (GROUNDCOVER_API_KEY, _BACKEND_ID, _API_URL, CUCUMBER_GROUNDCOVER_FILTER) ;
- champs_serveurs_mcp() : section « Serveurs MCP » (GROUNDCOVER_MCP_ENABLED, _URL, _HEADERS, _TOOLS) ;
- valider() : à l'enregistrement, analyse de « Connect to MCP » collé tel quel (adresse et en-têtes non secrets
  extraits, en-têtes secrets refusés) ; renvoie les valeurs à écrire dans le .env de l'agent, None si refusé ;
- etat_et_connexion() : état, « Se connecter à Groundcover » et « Tester », HORS formulaire (boutons).

Les champs renvoient les valeurs à écrire dans le .env de l'agent appelant ; le composant n'écrit rien. Une variable
transmise par le manager (SAVOYE_VARIABLES, agent_socle.config_commune) est affichée en lecture seule (un secret,
jamais sa valeur) et absente des valeurs renvoyées : elle n'est jamais réécrite.

Garde-fous (agent_socle.mcp_servers) : liste fermée de serveurs, outils de lecture seuls, aucun jeton dans le .env.
"""
import os

import streamlit as st

from agent_socle import auth_tools, config_commune, mcp_servers

API_KEY_ENV, BACKEND_ID_ENV, API_URL_ENV, FILTER_ENV = ("GROUNDCOVER_API_KEY", "GROUNDCOVER_BACKEND_ID",
                                                        "GROUNDCOVER_API_URL", "CUCUMBER_GROUNDCOVER_FILTER")
VARIABLES_API = (API_KEY_ENV, BACKEND_ID_ENV, API_URL_ENV, FILTER_ENV)
VARIABLES_MCP = (mcp_servers.ENABLED_ENV, mcp_servers.URL_ENV, mcp_servers.HEADERS_ENV, mcp_servers.TOOLS_ENV)
VARIABLES = VARIABLES_API + VARIABLES_MCP
SECRETS = (API_KEY_ENV,)
GEREE = " Transmise par le manager : se modifie dans le manager (onglet Configuration › Accès)."


def _texte(valeurs: dict, nom: str, label: str = "", **kwargs) -> None:
    """Champ texte de `nom`, ajouté à `valeurs` ; transmis par le manager : lecture seule, rien d'ajouté."""
    if config_commune.geree(nom):
        kwargs["help"] = (kwargs.get("help") or "").strip() + GEREE
        if nom in SECRETS:
            kwargs["placeholder"] = "transmise par le manager — non affichée"
        st.text_input(label or nom, value="" if nom in SECRETS else os.getenv(nom, ""), disabled=True,
                      type="password" if nom in SECRETS else "default", key=f"geree_{nom}", **kwargs)
        return
    if nom in SECRETS:
        valeurs[nom] = auth_tools.secret_field(st, nom, label, **kwargs).strip()
    else:
        valeurs[nom] = st.text_input(label or nom, value=os.getenv(nom, ""), **kwargs).strip()


def champs_acces_api() -> dict:
    """Accès à l'API Groundcover (logs de l'environnement de test, lecture seule) : valeurs à écrire dans le .env."""
    valeurs = {}
    st.markdown("**Logs de l'environnement de test dans groundcover** (lecture seule)")
    with st.container(horizontal=True):
        _texte(valeurs, API_KEY_ENV,
               help="Clé d'API groundcover (Settings → Access → API Keys), de préférence d'un compte en lecture seule.")
        _texte(valeurs, BACKEND_ID_ENV,
               help="Identifiant du backend (comptes multi-backend seulement, même écran que la clé).")
        _texte(valeurs, API_URL_ENV, placeholder="https://api.groundcover.com")
    _texte(valeurs, FILTER_ENV, placeholder="namespace:apparel-cucumber",
           help="Filtre gcQL de l'environnement où Jenkins joue les tests (namespace, workload, cluster…), ajouté à "
                "toute requête : obligatoire, sans lui les logs groundcover ne sont pas lus.")
    return valeurs


def champs_serveurs_mcp(compte: str = "compte Claude de l'agent") -> dict:
    """
    Section « Serveurs MCP » : Groundcover seul, pour les étapes de diagnostic. `compte` : où l'agent appelant désigne
    son compte Claude (dossier de configuration où la connexion est conservée). Valeurs à écrire dans le .env.
    """
    valeurs = {}
    st.markdown("#### :material/hub: Serveurs MCP")
    st.caption("Par défaut, les appels Claude de l'agent ne chargent aucun serveur MCP (--strict-mcp-config). "
               "Seul Groundcover peut être ajouté, en lecture des logs serveur, pour les étapes de diagnostic "
               "(échecs d'un run, correction de l'init, correction après exécution) ; jamais pour l'analyse d'un "
               "ticket ni la génération d'un patch. Aucun jeton dans le .env : la connexion se fait par "
               f"navigateur et reste dans le dossier de configuration de Claude Code ({compte}).")
    enabled_help = ("GROUNDCOVER_MCP_ENABLED : donne le serveur MCP Groundcover (outils de lecture seulement) aux "
                    "étapes de diagnostic.")
    active = os.getenv(mcp_servers.ENABLED_ENV, "").strip() == "1"
    if config_commune.geree(mcp_servers.ENABLED_ENV):
        st.checkbox("Groundcover activé", value=active, disabled=True, help=enabled_help + GEREE,
                    key=f"geree_{mcp_servers.ENABLED_ENV}")
    else:
        valeurs[mcp_servers.ENABLED_ENV] = "1" if st.checkbox("Groundcover activé", value=active,
                                                              help=enabled_help) else "0"
    _texte(valeurs, mcp_servers.URL_ENV, "Adresse du serveur MCP Groundcover",
           placeholder="Adresse donnée par « Connect to MCP » dans Groundcover",
           help="GROUNDCOVER_MCP_URL. Collez l'adresse, ou la commande / la configuration JSON proposée par « Connect "
                "to MCP » : l'adresse et les en-têtes non secrets en sont extraits à l'enregistrement. Un en-tête "
                "d'authentification (jeton, clé) est refusé.")
    with st.container(horizontal=True):
        _texte(valeurs, mcp_servers.HEADERS_ENV, "En-têtes non secrets (facultatif)",
               placeholder="Nom: valeur ; Nom: valeur",
               help="GROUNDCOVER_MCP_HEADERS : en-têtes demandés par « Connect to MCP » (fuseau horaire, "
                    "identifiant de tenant…). Jamais de jeton.")
        _texte(valeurs, mcp_servers.TOOLS_ENV, "Outils autorisés (facultatif)",
               placeholder="Vide : outils de lecture relevés par « Tester »",
               help="GROUNDCOVER_MCP_TOOLS : noms complets (mcp__groundcover__…), séparés par des virgules. Seuls "
                    "les outils de lecture (get, list, query, search…) sont gardés.")
    return valeurs


def preparer(valeurs: dict) -> dict:
    """
    Valeurs à enregistrer (sans Streamlit) : « Connect to MCP » collé tel quel dans l'adresse → adresse et en-têtes
    non secrets extraits, en-têtes secrets écartés. Renvoie {"valeurs", "erreur" (adresse refusée : rien à
    enregistrer), "refuses" (en-têtes d'authentification écartés)}. Les variables du manager restent écartées.
    """
    valeurs = {nom: valeur for nom, valeur in (valeurs or {}).items() if not config_commune.geree(nom)}
    url = valeurs.get(mcp_servers.URL_ENV)
    if not url:
        return {"valeurs": valeurs, "erreur": "", "refuses": []}
    connect = mcp_servers.parse_connect(url)
    if connect["erreur"]:
        return {"valeurs": valeurs, "erreur": f"Adresse Groundcover refusée : {connect['erreur']}.", "refuses": []}
    valeurs[mcp_servers.URL_ENV] = connect["url"]
    headers = {**connect["headers"], **mcp_servers.parse_headers(valeurs.get(mcp_servers.HEADERS_ENV, ""))}
    secret = mcp_servers.secret_headers(headers)
    if mcp_servers.HEADERS_ENV in valeurs:
        valeurs[mcp_servers.HEADERS_ENV] = mcp_servers.format_headers(
            {k: v for k, v in headers.items() if k not in secret})
    return {"valeurs": valeurs, "erreur": "", "refuses": connect["refuses"] + secret}


def valider(valeurs: dict):
    """
    À l'enregistrement du formulaire : preparer() et ses messages. Renvoie les valeurs à écrire dans le .env de
    l'agent (variables du manager écartées), ou None si l'adresse est refusée (« Configuration non enregistrée »).
    """
    resultat = preparer(valeurs)
    if resultat["refuses"]:
        st.warning("En-têtes d'authentification non enregistrés (aucun jeton dans le .env) : "
                   + ", ".join(resultat["refuses"]) + ". La connexion se fait par navigateur "
                   "(« Se connecter à Groundcover »).", icon=":material/key_off:")
    if resultat["erreur"]:
        st.error(resultat["erreur"] + " Configuration non enregistrée.", icon=":material/error:")
        return None
    return resultat["valeurs"]


def etat_et_connexion() -> None:
    """État de Groundcover (MCP), « Se connecter à Groundcover » (console Claude Code) et « Tester » : hors formulaire."""
    state = mcp_servers.status()
    label = mcp_servers.STATUS_LABELS.get(state["statut"], state["statut"])
    with st.container(horizontal=True, vertical_alignment="center"):
        connect_clicked = st.button("Se connecter à Groundcover", icon=":material/login:",
                                    disabled=not mcp_servers.configured(), key="groundcover_mcp_login")
        test_clicked = st.button("Tester", icon=":material/lan:", disabled=not mcp_servers.configured(),
                                 key="groundcover_mcp_test")
        st.caption(f"Groundcover (MCP) : {label}" + (f" — {state['date'].replace('T', ' ')}" if state.get("date") else "")
                   + (f" — {state['message']}" if state.get("message") else "")
                   + (f" — {len(mcp_servers.allowed_tools())} outil(s) de lecture autorisé(s)"
                      if state["statut"] in ("connecté", "désactivé") and mcp_servers.allowed_tools() else ""))
    if connect_clicked:
        try:
            st.info(mcp_servers.open_login_console(), icon=":material/login:")
        except (OSError, ValueError) as e:
            st.error(f"Console non ouverte : {e}", icon=":material/error:")
    if test_clicked:
        with st.spinner("Test de Groundcover (démarrage de Claude Code, puis un appel de lecture)…"):
            try:
                result = mcp_servers.test_connection()
            except ValueError as e:
                result = {"statut": "erreur", "message": str(e)}
        message = f"Groundcover : {mcp_servers.STATUS_LABELS.get(result['statut'], result['statut'])}" + (
            f" — {result['message']}" if result.get("message") else "")
        if result["statut"] == "connecté":
            st.success(message, icon=":material/check_circle:")
        elif result["statut"] == "expiré":
            st.warning(message + " Cliquez « Se connecter à Groundcover ».", icon=":material/key_off:")
        else:
            st.error(message, icon=":material/error:")
