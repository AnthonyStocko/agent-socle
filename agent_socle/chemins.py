"""Emplacement des données partagées des agents : .tmp/, .env et fichiers produits.

AGENT_DATA_DIR : dossier qui contient .tmp/ et .env. Par défaut, le dépôt agent-scrum-master voisin du socle
(C:\agent-socle → C:\agent-scrum-master), c'est-à-dire l'emplacement actuel des données : aucune migration.
"""
import os

_DEFAUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "agent-scrum-master")
DATA_DIR = os.path.abspath(os.getenv("AGENT_DATA_DIR", "").strip() or _DEFAUT)
