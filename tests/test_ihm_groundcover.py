"""
Composant commun de la configuration Groundcover (agent_socle.ihm_groundcover) : champs de l'accès API et des serveurs
MCP, valeurs renvoyées à l'agent appelant, variables du manager en lecture seule et jamais renvoyées, « Connect to MCP »
analysé à l'enregistrement (aucun jeton gardé), désignation de la page dans les messages de mcp_servers.
"""
import pytest
from streamlit.testing.v1 import AppTest

from agent_socle import config_commune, ihm_groundcover, mcp_servers

URL = "https://mcp.groundcover.com/api/mcp"


@pytest.fixture(autouse=True)
def _sans_manager(monkeypatch):
    for nom in ihm_groundcover.VARIABLES + (mcp_servers.PAGE_ENV, config_commune.VARIABLE_LISTE):
        monkeypatch.delenv(nom, raising=False)
    monkeypatch.delenv("AGENT_AUTH", raising=False)
    config_commune.relever({})
    yield
    config_commune.relever({})


def _page():
    import streamlit as st
    from agent_socle import ihm_groundcover
    with st.form("f"):
        valeurs = {**ihm_groundcover.champs_acces_api(), **ihm_groundcover.champs_serveurs_mcp()}
        envoye = st.form_submit_button("Enregistrer")
    st.session_state["valeurs"] = valeurs
    if envoye:
        st.session_state["a_ecrire"] = ihm_groundcover.valider(valeurs)


def _app():
    at = AppTest.from_function(_page, default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _champ(at, label):
    return next(t for t in at.text_input if t.label == label)


# ---------------------------------------------------------------------------
# preparer : « Connect to MCP » analysé, aucun jeton gardé
# ---------------------------------------------------------------------------

def test_adresse_seule_gardee_telle_quelle():
    r = ihm_groundcover.preparer({mcp_servers.URL_ENV: URL, mcp_servers.HEADERS_ENV: ""})
    assert r == {"valeurs": {mcp_servers.URL_ENV: URL, mcp_servers.HEADERS_ENV: ""}, "erreur": "", "refuses": []}


def test_commande_connect_en_tetes_secrets_refuses():
    commande = (f'claude mcp add groundcover --transport http {URL} --header "Authorization: Bearer abc" '
                f'--header "X-Timezone: Europe/Paris"')
    r = ihm_groundcover.preparer({mcp_servers.URL_ENV: commande, mcp_servers.HEADERS_ENV: "X-Tenant: t1 ; X-Api-Key: k"})
    assert r["erreur"] == "" and sorted(r["refuses"]) == ["Authorization", "X-Api-Key"]
    assert r["valeurs"][mcp_servers.URL_ENV] == URL
    assert r["valeurs"][mcp_servers.HEADERS_ENV] == "X-Timezone: Europe/Paris ; X-Tenant: t1"
    assert "abc" not in str(r["valeurs"]) and ": k" not in str(r["valeurs"])


def test_adresse_jira_refusee():
    r = ihm_groundcover.preparer({mcp_servers.URL_ENV: "https://x.atlassian.net/mcp"})
    assert r["erreur"].startswith("Adresse Groundcover refusée : serveur Jira / Atlassian refusé")


def test_variables_du_manager_jamais_renvoyees():
    config_commune.relever({config_commune.VARIABLE_LISTE: "GROUNDCOVER_API_KEY,GROUNDCOVER_MCP_HEADERS",
                            "GROUNDCOVER_API_KEY": "cle-manager", "GROUNDCOVER_MCP_HEADERS": "X-A: 1"})
    r = ihm_groundcover.preparer({"GROUNDCOVER_API_KEY": "autre", mcp_servers.HEADERS_ENV: "X-B: 2",
                                  mcp_servers.URL_ENV: f'{URL} --header "X-C: 3"'})
    assert r["valeurs"] == {mcp_servers.URL_ENV: URL}


# ---------------------------------------------------------------------------
# Composant Streamlit
# ---------------------------------------------------------------------------

def test_champs_renvoient_les_valeurs_du_env(monkeypatch):
    monkeypatch.setenv("GROUNDCOVER_API_URL", " https://api.groundcover.com ")
    monkeypatch.setenv("GROUNDCOVER_API_KEY", "cle")
    monkeypatch.setenv(mcp_servers.ENABLED_ENV, "1")
    at = _app()
    assert at.session_state["valeurs"] == {
        "GROUNDCOVER_API_KEY": "cle", "GROUNDCOVER_BACKEND_ID": "", "GROUNDCOVER_API_URL": "https://api.groundcover.com",
        "CUCUMBER_GROUNDCOVER_FILTER": "", mcp_servers.ENABLED_ENV: "1", mcp_servers.URL_ENV: "",
        mcp_servers.HEADERS_ENV: "", mcp_servers.TOOLS_ENV: ""}
    assert [m for m in at.markdown if "Serveurs MCP" in m.value]


def test_variables_du_manager_en_lecture_seule(monkeypatch):
    environ = {config_commune.VARIABLE_LISTE: "GROUNDCOVER_API_KEY,GROUNDCOVER_API_URL,GROUNDCOVER_MCP_ENABLED",
               "GROUNDCOVER_API_KEY": "cle-secrete-manager", "GROUNDCOVER_API_URL": "https://api.manager",
               "GROUNDCOVER_MCP_ENABLED": "1"}
    config_commune.relever(environ)
    for nom in ("GROUNDCOVER_API_KEY", "GROUNDCOVER_API_URL", "GROUNDCOVER_MCP_ENABLED"):
        monkeypatch.setenv(nom, environ[nom])
    at = _app()
    cle, adresse = _champ(at, "GROUNDCOVER_API_KEY"), _champ(at, "GROUNDCOVER_API_URL")
    assert cle.disabled and adresse.disabled and at.checkbox[0].disabled and at.checkbox[0].value
    # Secret du manager jamais renvoyé au navigateur ; valeur non secrète affichée
    assert cle.value == "" and adresse.value == "https://api.manager"
    assert not {"GROUNDCOVER_API_KEY", "GROUNDCOVER_API_URL", "GROUNDCOVER_MCP_ENABLED"} & set(at.session_state["valeurs"])
    assert "GROUNDCOVER_BACKEND_ID" in at.session_state["valeurs"]


def test_enregistrement_connect_to_mcp(monkeypatch):
    at = _app()
    _champ(at, "Adresse du serveur MCP Groundcover").input(f'claude mcp add groundcover {URL} '
                                                           f'--header "Authorization: Bearer abc"')
    at.button[0].click().run()
    assert at.session_state["a_ecrire"][mcp_servers.URL_ENV] == URL
    assert at.session_state["a_ecrire"][mcp_servers.HEADERS_ENV] == ""
    assert "Authorization" in at.warning[0].value


def test_adresse_refusee_rien_a_ecrire():
    at = _app()
    _champ(at, "Adresse du serveur MCP Groundcover").input("https://x.atlassian.net/mcp")
    at.button[0].click().run()
    assert at.session_state["a_ecrire"] is None
    assert "Configuration non enregistrée" in at.error[0].value


def test_etat_et_connexion_sans_configuration():
    def page():
        from agent_socle import ihm_groundcover
        ihm_groundcover.etat_et_connexion()
    at = AppTest.from_function(page, default_timeout=30)
    at.run()
    assert not at.exception
    assert all(b.disabled for b in at.button)
    assert "Groundcover (MCP) : non configuré" in at.caption[0].value


# ---------------------------------------------------------------------------
# Désignation de la page dans les messages
# ---------------------------------------------------------------------------

def test_messages_neutres_par_defaut_puis_page_de_l_agent(monkeypatch, tmp_path):
    monkeypatch.setenv(mcp_servers.URL_ENV, URL)
    monkeypatch.setenv(mcp_servers.ENABLED_ENV, "1")
    assert "onglet ⚙️" not in mcp_servers.failure_message("expiré")
    assert mcp_servers.page() in mcp_servers.failure_message("expiré")
    assert mcp_servers.page() in mcp_servers.unavailable_reason(str(tmp_path))
    mcp_servers.definir_page("onglet Paramètres d'agent-cucumber")
    assert "(onglet Paramètres d'agent-cucumber, « Se connecter à Groundcover »)" in mcp_servers.failure_message("x")
    assert mcp_servers.unavailable_reason(str(tmp_path)).endswith("(onglet Paramètres d'agent-cucumber)")
    mcp_servers.definir_page("")
    assert mcp_servers.page() == mcp_servers.DEFAULT_PAGE
