"""
Registre local des livraisons de patchs : ``.tmp/livraisons.jsonl`` (non versionné), écrit par l'étape ``patch``.

Une ligne JSON par exécution réussie de l'étape qui a produit au moins un ``.patch`` :
``{"ticket", "date", "fichiers", "pieces_jointes", "verification"}``.
- ``fichiers`` : noms des ``.patch`` produits pendant l'exécution ;
- ``pieces_jointes`` : ceux qui sont bien en pièce jointe du ticket Jira. C'est Claude qui les joint (prompts
  ``patch.md`` et ``patch_cucumber.md``) : l'étape le VÉRIFIE ensuite par une simple lecture des pièces jointes ;
- ``verification`` : ``ok``, ou la raison pour laquelle Jira n'a pas pu être lu.

Lu par agent-manager-savoye (outil MCP ``patchs`` de ``mcp_lecture.py``, en lecture seule) pour son bloc « Patchs
livrés » : un ``.patch`` à la racine ne prouve pas une livraison, une pièce jointe vérifiée si.

Règles : écriture au mieux (``noter*`` ne lève jamais) ; aucune donnée nominative ni secret (clé, date, noms de
fichiers seulement) ; au plus LIGNES_MAX lignes gardées.
"""
from agent_socle.chemins import DATA_DIR
import json
import os
import re
from datetime import datetime, timedelta

WORKSPACE_DIR = DATA_DIR
FICHIER = os.path.join(WORKSPACE_DIR, ".tmp", "livraisons.jsonl")
CLE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
FICHIER_PATCH = re.compile(r"^[\w.-]+\.patch$")
LIGNES_MAX = 2000


class RegistreErreur(Exception):
    pass


def _nom(chemin: str) -> str:
    nom = os.path.basename(str(chemin or ""))
    return nom if FICHIER_PATCH.match(nom) else ""


def noter(ticket: str, fichiers, pieces_jointes, verification: str = "ok", quand: datetime | None = None,
          chemin: str = FICHIER) -> bool:
    """Ajoute une livraison au registre. Ne lève jamais : False si la ligne n'a pas pu être écrite."""
    cle = str(ticket or "").strip().upper()
    noms = list(dict.fromkeys(n for n in map(_nom, fichiers or []) if n))
    if not CLE.match(cle) or not noms:
        return False
    jointes = {_nom(p) for p in pieces_jointes or []}
    ligne = {"ticket": cle, "date": (quand or datetime.now()).isoformat(timespec="seconds"), "fichiers": noms,
             "pieces_jointes": [n for n in noms if n in jointes], "verification": str(verification or "")[:120]}
    try:
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        _borner(chemin)
    except OSError:
        return False
    return True


def _borner(chemin: str) -> None:
    with open(chemin, encoding="utf-8", errors="replace") as f:
        lignes = f.readlines()
    if len(lignes) > LIGNES_MAX:
        temporaire = chemin + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            f.writelines(lignes[-LIGNES_MAX:])
        os.replace(temporaire, chemin)


def noter_patch(ticket: str, fichiers, lire_pieces_jointes=None, chemin: str = FICHIER) -> bool:
    """Fin de l'étape ``patch`` : lit dans Jira les pièces jointes du ticket (LECTURE seule), puis note la livraison.
    Ne lève jamais."""
    if lire_pieces_jointes is None:
        from agent_socle.jira_tools import get_jira_attachment_names as lire_pieces_jointes
    try:
        jointes, verification = set(lire_pieces_jointes(str(ticket).strip().upper())), "ok"
    except Exception as e:  # Jira injoignable, non configuré… : la livraison est notée, non vérifiée
        jointes, verification = set(), f"Jira illisible ({type(e).__name__})"
    return noter(ticket, fichiers, jointes, verification, chemin=chemin)


def lire(jours: int = 7, chemin: str = FICHIER, maintenant: datetime | None = None) -> list[dict]:
    """Livraisons des ``jours`` derniers jours, de la plus récente à la plus ancienne. Lignes illisibles ignorées.
    Registre absent : liste vide. Lève RegistreErreur si le fichier existe mais ne peut pas être lu."""
    limite = ((maintenant or datetime.now()) - timedelta(days=jours)).isoformat(timespec="seconds")
    if not os.path.exists(chemin):
        return []
    try:
        with open(chemin, encoding="utf-8", errors="replace") as f:
            lignes = f.readlines()
    except OSError as e:
        raise RegistreErreur(f"registre des livraisons illisible ({type(e).__name__})") from e
    livraisons = []
    for brute in lignes:
        try:
            l = json.loads(brute)
        except ValueError:
            continue
        if not isinstance(l, dict) or not CLE.match(str(l.get("ticket", ""))) or str(l.get("date", "")) < limite:
            continue
        fichiers = [n for n in map(_nom, l.get("fichiers") or []) if n]
        if fichiers:
            livraisons.append({"ticket": l["ticket"], "date": str(l["date"]), "fichiers": fichiers,
                               "pieces_jointes": [n for n in map(_nom, l.get("pieces_jointes") or []) if n],
                               "verification": str(l.get("verification", ""))})
    # même seconde : la dernière ligne écrite d'abord (tri stable sur la liste inversée)
    return sorted(reversed(livraisons), key=lambda l: l["date"], reverse=True)
