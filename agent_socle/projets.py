"""Registre des projets : façade en lecture sur les sources existantes, sans migration.

Deux sources, lues à leur place actuelle :
- les projets Cucumber d'agent-scrum-master (``<AGENT_DATA_DIR>/.tmp/cucumber/<client>/projet.json``…),
  ``known_projects`` (extrait de tools/cucumber_detection.py, inchangé) ;
- les applications du manager (``commun.toml`` de ``SAVOYE_CONFIG_DIR``, défaut ``../agent-manager-savoye/config``),
  sans les secrets (le fichier n'en contient pas ; le .env du manager n'est jamais lu ici).

``registre()`` les assemble ; ``lire()`` interroge l'API d'agent-projets (``AGENT_PROJETS_API``, défaut
http://localhost:8512) et, si elle ne répond pas, lit les mêmes sources directement : même résultat.
"""
import json
import os
import tomllib
import urllib.error
import urllib.request

from agent_socle.chemins import DATA_DIR
from agent_socle.fichiers import _read_json

PROJECT_FILE = "projet.json"


def known_projects(cache_root: str) -> dict:
    """{client: réglages} des projets déjà travaillés (dossier de cache avec réglages, profil ou génération)."""
    out = {}
    if not os.path.isdir(cache_root):
        return out
    for name in sorted(os.listdir(cache_root)):
        folder = os.path.join(cache_root, name)
        if name.startswith(("_", ".")) or not os.path.isdir(folder):
            continue
        if not any(os.path.exists(os.path.join(folder, f)) for f in (PROJECT_FILE, "profil.json", "etat.json",
                                                                      "inventaire.json")):
            continue
        settings = _read_json(os.path.join(folder, PROJECT_FILE), {}) or {}
        if not settings.get("client_repo"):
            settings["client_repo"] = (_read_json(os.path.join(folder, "inventaire.json"), {}) or {}).get(
                "depot_client", "")
        out[name] = settings
    return out


# ---------------------------------------------------------------------------
# Applications du manager (commun.toml, lecture seule)
# ---------------------------------------------------------------------------

CUCUMBER_CACHE = os.path.join(DATA_DIR, ".tmp", "cucumber")
MANAGER_CONFIG = os.path.join(os.path.dirname(DATA_DIR), "agent-manager-savoye", "config")
API_DEFAUT = "http://localhost:8512"


def dossier_manager() -> str:
    return os.getenv("SAVOYE_CONFIG_DIR", "").strip() or MANAGER_CONFIG


def applications(dossier: str = "") -> dict:
    """{nom: application} de commun.toml (sources, base, logs, projet Jira, job Jenkins) ; {} si absent ou illisible."""
    chemin = os.path.join(dossier or dossier_manager(), "commun.toml")
    try:
        with open(chemin, "rb") as f:
            donnees = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {str(a.get("nom", "")): a for a in donnees.get("applications") or [] if a.get("nom")}


def registre(cache_root: str = "", dossier: str = "") -> dict:
    """{nom: {"cucumber": réglages|None, "application": application|None}} : les deux sources, sans fusion."""
    cucumber = known_projects(cache_root or CUCUMBER_CACHE)
    apps = applications(dossier)
    return {nom: {"cucumber": cucumber.get(nom), "application": apps.get(nom)}
            for nom in sorted(set(cucumber) | set(apps))}


# ---------------------------------------------------------------------------
# Client de l'API d'agent-projets (lecture), repli sur la lecture directe
# ---------------------------------------------------------------------------

def api() -> str:
    return (os.getenv("AGENT_PROJETS_API", "").strip() or API_DEFAUT).rstrip("/")


def lire(chemin: str = "/projets", delai: float = 2.0):
    """Réponse JSON de l'API (ex. /projets, /projets/<nom>) ; sans API joignable, la même donnée lue localement."""
    try:
        with urllib.request.urlopen(api() + chemin, timeout=delai) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return local(chemin)


def local(chemin: str):
    """Même réponse que l'API, calculée sur place."""
    if chemin.rstrip("/") == "/projets":
        return registre()
    if chemin.startswith("/projets/"):
        return registre().get(chemin.split("/", 2)[2])
    if chemin.rstrip("/") == "/sante":
        return {"ok": True, "source": "locale"}
    return None
