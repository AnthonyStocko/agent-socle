"""
Configuration commune tenue par agent-manager-savoye.

Quand le manager lance l'agent, il lui transmet en variables d'environnement les accès communs et les secrets
qui lui reviennent (Jira, Bitbucket, Jenkins, groundcover, compte Claude), et leur liste dans SAVOYE_VARIABLES.
Ces variables l'emportent sur le .env : l'IHM recharge le .env avec override=True à chaque interaction, puis
appelle reappliquer(). L'onglet Configuration ne les réécrit pas dans le .env : elles se modifient dans le
manager.

Les valeurs sont relevées UNE fois, au premier import du module (avant tout load_dotenv) : Streamlit ré-exécute
app.py à chaque interaction, mais garde les modules importés.

Lancé seul, l'agent n'a pas SAVOYE_VARIABLES : rien ne change.
"""
import os

VARIABLE_LISTE = "SAVOYE_VARIABLES"
VARIABLE_DOSSIER = "SAVOYE_CONFIG_DIR"

_GEREES = {}


def relever(environ=None) -> dict:
    """Relève les variables transmises par le manager (appelé à l'import)."""
    environ = os.environ if environ is None else environ
    noms = [n.strip() for n in environ.get(VARIABLE_LISTE, "").split(",") if n.strip()]
    _GEREES.clear()
    _GEREES.update({n: environ[n] for n in noms if environ.get(n)})
    return dict(_GEREES)


def reappliquer() -> None:
    """Remet les valeurs du manager dans l'environnement, après un load_dotenv(override=True)."""
    os.environ.update(_GEREES)


def geree(nom: str) -> bool:
    return nom in _GEREES


def gerees() -> list:
    return sorted(_GEREES)


relever()
