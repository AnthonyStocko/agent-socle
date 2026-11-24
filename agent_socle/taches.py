"""
Travaux en cours des agents : chaque étape (`main.py --step …`) est lancée hors de la session Streamlit, par un
relais détaché (`python -m agent_socle.taches <agent> <id> -- <commande>`, Windows : CREATE_NEW_PROCESS_GROUP +
DETACHED_PROCESS) qui écrit sa sortie directement dans le journal de l'exécution (.tmp/logs/…) et dans le journal
technique, jamais dans un tube lié à la page : fermer le navigateur n'interrompt pas le traitement.

Registre : un fichier par tâche, .tmp/taches/<agent>/<id>.json — agent, étape, arguments, cible (ticket ou client),
auteur, PID, début, statut (en_cours, terminee, echec, interrompue, arretee), fin, code retour, journal, contexte de
la page au lancement. Une tâche en_cours dont le processus n'existe plus passe en interrompue (`actualiser`).
Contexte de page par auteur : .tmp/sessions/<auteur>/<agent>.json (enregistré puis rechargé à la reconnexion).
Dossiers surchargeables (tests) : AGENT_TACHES_DIR, AGENT_SESSIONS_DIR.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime

from agent_socle.chemins import DATA_DIR
from agent_socle.verrou import process_info

STATUTS = ("en_cours", "terminee", "echec", "interrompue", "arretee")
JOURNAL_MAX_BYTES = 5_000_000
# Options de --step qui désignent la cible d'une tâche (ticket, client, fonctionnalité)
OPTIONS_CIBLE = ("--issue", "--client-name", "--feature", "--pr-url", "--project")


def taches_dir() -> str:
    return os.getenv("AGENT_TACHES_DIR") or os.path.join(DATA_DIR, ".tmp", "taches")


def sessions_dir() -> str:
    return os.getenv("AGENT_SESSIONS_DIR") or os.path.join(DATA_DIR, ".tmp", "sessions")


def _maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _nom(texte: str) -> str:
    return re.sub(r"[^\w.-]", "_", (texte or "").strip()) or "local"


def chemin(agent: str, ident: str) -> str:
    return os.path.join(taches_dir(), _nom(agent), f"{_nom(ident)}.json")


def _ecrire(tache: dict) -> None:
    path = chemin(tache["agent"], tache["id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    provisoire = f"{path}.{os.getpid()}.tmp"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(tache, f, ensure_ascii=False, indent=2)
    os.replace(provisoire, path)


def lire(agent: str, ident: str) -> dict:
    try:
        with open(chemin(agent, ident), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def option(cmd: list, nom: str) -> str:
    return cmd[cmd.index(nom) + 1] if nom in cmd and cmd.index(nom) + 1 < len(cmd) else ""


def etape(cmd: list) -> str:
    return option(cmd, "--step") or "main"


def cible(cmd: list) -> str:
    return next((option(cmd, o) for o in OPTIONS_CIBLE if option(cmd, o)), "")


def nouvel_identifiant() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def lancer(agent: str, cmd: list, journal: str, journal_technique: str, auteur: str = "", contexte: dict = None,
           env: dict = None, cwd: str = None) -> tuple:
    """Enregistre la tâche et lance son relais détaché ; renvoie (processus, tâche)."""
    tache = {"id": nouvel_identifiant(), "agent": agent, "etape": etape(cmd), "arguments": list(cmd[1:]),
             "cible": cible(cmd), "auteur": auteur, "pid": 0, "depart": "", "debut": _maintenant(),
             "statut": "en_cours", "fin": "", "code_retour": None, "journal": journal,
             "journal_technique": journal_technique, "contexte": contexte or {}}
    _ecrire(tache)
    relais = [sys.executable, "-m", "agent_socle.taches", agent, tache["id"], "--", *cmd]
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} \
        if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(relais, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, cwd=cwd, env=env, close_fds=True, **options)
    pid = getattr(process, "pid", 0) or 0
    tache.update(pid=pid, depart=process_info(pid)[1] if pid else "")
    _ecrire(tache)
    return process, tache


def _ouvrir_journaux(tache: dict, cmd: list):
    technique, journal = tache["journal_technique"], tache["journal"]
    for path in (technique, journal):
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(technique) and os.path.getsize(technique) > JOURNAL_MAX_BYTES:
        os.replace(technique, technique + ".1")
    j, r = open(technique, "a", encoding="utf-8"), open(journal, "w", encoding="utf-8")
    j.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} — {' '.join(cmd[1:])[:300]}\n")
    r.write(f"===== {' '.join(cmd[1:])[:300]}\n")
    if tache.get("auteur"):
        j.write(f"===== lancé par {tache['auteur']}\n")
        r.write(f"===== lancé par {tache['auteur']}\n")
    return j, r


def relayer(tache: dict, cmd: list, lignes, attendre, on_line=None) -> int:
    """Écrit chaque ligne de la sortie dans le journal technique et celui de l'exécution, puis termine la tâche."""
    j, r = _ouvrir_journaux(tache, cmd)
    with j, r:
        for line in lignes:
            j.write(line)
            r.write(line)
            j.flush()
            r.flush()
            if on_line:
                on_line(line)
        code = attendre()
        j.write(f"===== code retour {code} — journal de l'exécution : {tache['journal']}\n")
        r.write(f"===== code retour {code}\n")
    terminer(tache["agent"], tache["id"], code)
    return code


def terminer(agent: str, ident: str, code: int) -> dict:
    tache = lire(agent, ident)
    if tache and tache.get("statut") == "en_cours":
        tache.update(statut="terminee" if code == 0 else "echec", fin=_maintenant(), code_retour=code)
        _ecrire(tache)
    return tache


def vivante(tache: dict) -> bool:
    pid = int(tache.get("pid") or 0)
    if not pid:
        return False
    alive, start = process_info(pid)
    return alive and not (tache.get("depart") and start and tache["depart"] != start)


def actualiser(tache: dict) -> dict:
    """Tâche en_cours dont le processus n'existe plus : interrompue."""
    if tache.get("statut") == "en_cours" and not vivante(tache):
        tache.update(statut="interrompue", fin=_maintenant())
        _ecrire(tache)
    return tache


def lister(agent: str = "", auteur: str = "") -> list:
    """Tâches (d'un agent, sinon de tous), actualisées : celles de l'auteur d'abord, puis les plus récentes."""
    racine = taches_dir()
    dossiers = [os.path.join(racine, _nom(agent))] if agent else \
        ([os.path.join(racine, d) for d in sorted(os.listdir(racine))] if os.path.isdir(racine) else [])
    taches = []
    for dossier in dossiers:
        if not os.path.isdir(dossier):
            continue
        for nom in os.listdir(dossier):
            if nom.endswith(".json"):
                tache = lire(os.path.basename(dossier), nom[:-5])
                if tache:
                    taches.append(actualiser(tache))
    taches.sort(key=lambda t: t.get("debut", ""), reverse=True)
    taches.sort(key=lambda t: (t.get("auteur") != auteur) if auteur else False)
    return taches


def arreter(agent: str, ident: str) -> dict:
    """Arrête la tâche (relais et étape, arbre de processus) ; statut arretee."""
    tache = lire(agent, ident)
    if not tache or tache.get("statut") != "en_cours":
        return tache
    pid = int(tache.get("pid") or 0)
    if pid and vivante(tache):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(pid, 15)
            except OSError:
                pass
    tache.update(statut="arretee", fin=_maintenant())
    _ecrire(tache)
    return tache


def duree(tache: dict) -> str:
    try:
        debut = datetime.fromisoformat(tache["debut"])
        fin = datetime.fromisoformat(tache["fin"]) if tache.get("fin") else datetime.now()
    except (KeyError, ValueError):
        return ""
    secondes = int((fin - debut).total_seconds())
    return f"{secondes // 3600} h {secondes % 3600 // 60:02d} min" if secondes >= 3600 else \
        f"{secondes // 60} min {secondes % 60:02d} s"


def fin_du_journal(tache: dict, lignes: int = 20) -> str:
    try:
        with open(tache.get("journal", ""), encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lignes:])
    except OSError:
        return ""


def chemin_contexte(auteur: str, agent: str) -> str:
    return os.path.join(sessions_dir(), _nom(auteur), f"{_nom(agent)}.json")


def enregistrer_contexte(auteur: str, agent: str, valeurs: dict) -> None:
    """Choix de la page nécessaires pour y revenir (valeurs JSON seulement)."""
    propres = {}
    for cle, valeur in (valeurs or {}).items():
        try:
            json.dumps(valeur)
        except (TypeError, ValueError):
            continue
        propres[cle] = valeur
    path = chemin_contexte(auteur, agent)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(propres, f, ensure_ascii=False, indent=2)


def charger_contexte(auteur: str, agent: str) -> dict:
    try:
        with open(chemin_contexte(auteur, agent), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def main(argv: list) -> int:
    """Relais : `python -m agent_socle.taches <agent> <id> -- <commande>`."""
    agent, ident, separateur, *cmd = argv
    assert separateur == "--" and cmd, "usage : python -m agent_socle.taches <agent> <id> -- <commande>"
    tache = lire(agent, ident)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               text=True, encoding="utf-8", errors="replace")
    tache["pid_etape"] = process.pid
    _ecrire(tache)
    return relayer(tache, cmd, process.stdout, process.wait)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
