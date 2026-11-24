"""Configuration commune d'agent-manager-savoye : les variables transmises l'emportent sur le .env."""
import os
from unittest import mock

from dotenv import load_dotenv

from agent_socle import config_commune


def test_variables_du_manager_prioritaires_sur_le_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JIRA_API_TOKEN=du-env\nJIRA_EMAIL=moi@exemple.com\n", encoding="utf-8")
    lancement = {"SAVOYE_VARIABLES": "JIRA_API_TOKEN,JIRA_DOMAIN,VIDE", "JIRA_API_TOKEN": "du-manager",
                 "JIRA_DOMAIN": "societe.atlassian.net", "VIDE": ""}
    with mock.patch.dict(os.environ, lancement):
        assert config_commune.relever() == {"JIRA_API_TOKEN": "du-manager", "JIRA_DOMAIN": "societe.atlassian.net"}
        for _ in range(2):                                   # chaque interaction Streamlit recharge le .env
            load_dotenv(env, override=True)
            assert os.environ["JIRA_API_TOKEN"] == "du-env"
            config_commune.reappliquer()
            assert os.environ["JIRA_API_TOKEN"] == "du-manager"
            assert os.environ["JIRA_EMAIL"] == "moi@exemple.com"   # non transmis : le .env reste
        assert config_commune.geree("JIRA_API_TOKEN") and not config_commune.geree("JIRA_EMAIL")
        assert config_commune.gerees() == ["JIRA_API_TOKEN", "JIRA_DOMAIN"]
    config_commune.relever({})


def test_lance_seul_rien_ne_change(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JIRA_API_TOKEN=du-env\n", encoding="utf-8")
    with mock.patch.dict(os.environ, {"JIRA_API_TOKEN": "du-shell"}):
        os.environ.pop("SAVOYE_VARIABLES", None)
        assert config_commune.relever() == {}
        load_dotenv(env, override=True)
        config_commune.reappliquer()
        assert os.environ["JIRA_API_TOKEN"] == "du-env"
        assert not config_commune.gerees()
