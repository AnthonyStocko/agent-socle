"""
Verrou de génération Cucumber, en lecture (lecteur du manager) : détenteur vivant du verrou d'un client.
LOCK_NAME, _windows_process, process_info et describe sont extraits tels quels de tools/cucumber_lock.py ;
`holder` en est une copie qui lit le verrou à son emplacement (.tmp/cucumber/<client> de AGENT_DATA_DIR).
La prise et la libération du verrou restent dans agent-cucumber.
"""
import json
import os
import sys

from agent_socle.projets import CUCUMBER_CACHE


LOCK_NAME = "generation.lock"


def _windows_process(pid: int):
    """(vivant, empreinte de démarrage) d'un processus Windows ; (False, '') s'il n'existe plus."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        # Accès refusé : le processus existe (autre utilisateur)
        return ctypes.get_last_error() == 5, ""
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return False, ""
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return True, ""
        return True, f"{times[0].dwHighDateTime}:{times[0].dwLowDateTime}"
    finally:
        kernel.CloseHandle(handle)


def process_info(pid: int):
    """(vivant, empreinte de démarrage) ; l'empreinte distingue un PID réutilisé par un autre processus."""
    if not pid or pid <= 0:
        return False, ""
    if sys.platform == "win32":
        return _windows_process(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False, ""
    except PermissionError:
        return True, ""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return True, f.read().rsplit(")", 1)[-1].split()[19]
    except (OSError, IndexError):
        return True, ""


def describe(data: dict) -> str:
    return (f"génération en cours (processus {data.get('pid')}, lancée le {str(data.get('debut', ''))[:19]}"
            + (f" : {data['commande']}" if data.get("commande") else "") + ")")


def lock_path(client: str) -> str:
    """Fichier du verrou d'un client (lecture seule : le dossier n'est pas créé)."""
    return os.path.join(CUCUMBER_CACHE, client, LOCK_NAME)


def holder(client: str) -> dict:
    """Détenteur vivant du verrou du client ; {} si libre (verrou absent, illisible ou d'un processus terminé)."""
    try:
        with open(lock_path(client), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    alive, start = process_info(int(data.get("pid") or 0))
    if not alive or (data.get("depart") and start and data["depart"] != start):
        return {}
    return data
