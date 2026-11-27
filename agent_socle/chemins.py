"""Emplacement des données partagées des agents : .tmp/, .env et fichiers produits.

AGENT_DATA_DIR (variable d'environnement système, pas dans le .env qui est lui-même dans ce dossier) : à définir.
À défaut : dossier agent-data voisin du socle (installation éditable seulement), puis l'ancien agent-scrum-master
le temps de la migration.
"""
import os
import warnings

_VOISINS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NOUVEAU = os.path.join(_VOISINS, "agent-data")
_ANCIEN = os.path.join(_VOISINS, "agent-scrum-master")


def _data_dir() -> str:
    configure = os.getenv("AGENT_DATA_DIR", "").strip()
    if configure:
        return os.path.abspath(configure)
    if not os.path.isdir(_NOUVEAU) and os.path.isfile(os.path.join(_ANCIEN, ".env")):
        warnings.warn(f"AGENT_DATA_DIR non défini : données lues dans l'ancien dossier {_ANCIEN}. "
                      "Définissez AGENT_DATA_DIR.", stacklevel=2)
        return _ANCIEN
    if not os.path.isdir(_NOUVEAU):
        warnings.warn(f"AGENT_DATA_DIR non défini et {_NOUVEAU} absent : aucune donnée (.env, mémoire) "
                      "ne sera trouvée.", stacklevel=2)
    return _NOUVEAU


DATA_DIR = _data_dir()