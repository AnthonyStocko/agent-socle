import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Client fictif des tests : ces valeurs ne doivent jamais apparaître dans le code (test_no_client_literals)
CLIENT = "clientx"
CLIENT_TAG = "@CLIENTX"
CLEAR = "init-data-rest-clear-main-x"
SITES = ("SITEA", "SITEB")
OWNERS = ("DO-1", "DO-2")
SECTORS = ("SECT_1", "SECT_MVT", "SECT_STOCK")
FICTIVE_VALUES = (CLIENT, CLIENT_TAG, CLEAR, *SITES, *OWNERS, *SECTORS)


def git(repo, *args):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


@pytest.fixture
def repo(tmp_path):
    """Dépôt git vide avec une identité locale, sur la branche integration."""
    path = str(tmp_path / "repo")
    os.makedirs(path)
    git(path, "init", "-q", "-b", "integration")
    git(path, "config", "user.name", "test")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "core.autocrlf", "false")
    return path


def pytest_configure(config):
    config.addinivalue_line("markers", "real_compile: contrôle de compilation des livraisons réellement exécuté")


@pytest.fixture(autouse=True)
def _isolated_knowledge(tmp_path, monkeypatch):
    """
    Connaissances partagées des tests dans un répertoire temporaire : jamais le vrai répertoire partagé
    (AGENT_KNOWLEDGE_DIR du .env), où les documents du client fictif seraient injectés dans le travail sur un vrai
    client. File d'attente et index aussi temporaires. app.py recharge le .env avec override=True à chaque exécution
    (AppTest) : ce rechargement ne peut plus remettre le vrai répertoire.
    """
    import dotenv
    from agent_socle import knowledge_tools
    monkeypatch.setenv("AGENT_KNOWLEDGE_DIR", str(tmp_path / "connaissances_partagees"))
    # Groundcover (MCP) jamais actif par le .env du poste : les tests qui en ont besoin l'activent eux-mêmes
    monkeypatch.setenv("GROUNDCOVER_MCP_ENABLED", "0")
    # Arguments du job Jenkins jamais lus par le contrôle des fichiers du lot (aucun appel réseau en test)
    monkeypatch.setenv("CUCUMBER_JOB_VALUES_CHECK", "0")
    # Journaux des exécutions lancées par l'interface (AppTest) : jamais dans le vrai .tmp/logs ni le journal technique
    monkeypatch.setenv("AGENT_RUN_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AGENT_JOURNAL_PATH", str(tmp_path / "journal_technique.log"))
    # Aucune requête réelle : sélection des données de test et contrôle de version de la base source désactivés
    # (les tests qui en ont besoin passent leur propre requête) ; cumul de coût des sessions temporaire
    monkeypatch.setenv("CUCUMBER_TEST_SELECTION", "0")
    monkeypatch.setenv("CUCUMBER_ANTICIPATION", "0")
    monkeypatch.setenv("CUCUMBER_BUSINESS_RULES", "0")
    monkeypatch.setenv("ESTIMATION_ENABLED", "0")
    monkeypatch.setenv("CUCUMBER_CLEANUP", "0")
    monkeypatch.setenv("CUCUMBER_CLEANUP_PROOF", "0")
    monkeypatch.setenv("ESTIMATION_SETTINGS_FILE", str(tmp_path / "estimation_projets.json"))
    monkeypatch.setenv("CUCUMBER_SOURCE_VERSION_CHECK", "0")
    monkeypatch.setattr(knowledge_tools, "OUTBOX_DIR", str(tmp_path / "knowledge_outbox"))
    monkeypatch.setattr(knowledge_tools, "INDEX_CACHE", str(tmp_path / "knowledge_index.json"))
    original = dotenv.load_dotenv

    def guarded(*args, **kwargs):
        kept = {name: os.environ.get(name) for name in ("AGENT_KNOWLEDGE_DIR", "GROUNDCOVER_MCP_ENABLED",
                                                         "CUCUMBER_JOB_VALUES_CHECK", "AGENT_RUN_LOGS_DIR",
                                                         "AGENT_JOURNAL_PATH", "CUCUMBER_TEST_SELECTION", "CUCUMBER_ANTICIPATION", "CUCUMBER_BUSINESS_RULES", "ESTIMATION_ENABLED", "ESTIMATION_SETTINGS_FILE", "CUCUMBER_CLEANUP", "CUCUMBER_CLEANUP_PROOF",
                                                         "CUCUMBER_SOURCE_VERSION_CHECK")}
        try:
            return original(*args, **kwargs)
        finally:
            for name, value in kept.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    monkeypatch.setattr(dotenv, "load_dotenv", guarded)
