"""
Valeurs par défaut des réglages Cucumber affichées par la page Configuration (et relues par agent-cucumber),
extraites telles quelles de tools/cucumber_tools.py, cucumber_verify.py et cucumber_java21.py.
"""
import os


DEFAULT_STD_MATCH_MIN = 0.4


DEFAULT_INLINE_STEP_CODE_CHARS = 16_000


DEFAULT_COMPILE_CMD = "mvn -q -o test-compile"


DEFAULT_INLINE_MAX_CHARS = 24_000


DEFAULT_INLINE_STUDIO_LINES = 150


DEFAULT_DUP_THRESHOLD = 0.85


def jenkins_credentials() -> bool:
    """JENKINS_USER et JENKINS_API_TOKEN renseignés."""
    return bool(os.getenv("JENKINS_USER", "").strip() and os.getenv("JENKINS_API_TOKEN", "").strip())


def agent_runs_tests() -> bool:
    """
    CUCUMBER_AGENT_JENKINS : l'agent exécute-t-il lui-même des tests pendant la génération (job Jenkins, branche de
    travail poussée, commande locale) ? Boucle fermée par défaut : 1 quand JENKINS_USER et JENKINS_API_TOKEN sont
    renseignés, 0 sinon (il livre alors un patch non vérifié). Une valeur 0 ou 1 explicite prime.
    """
    value = os.getenv("CUCUMBER_AGENT_JENKINS", "").strip()
    return value == "1" if value in ("0", "1") else jenkins_credentials()


DEFAULT_REFERENCE_DAYS = 7
