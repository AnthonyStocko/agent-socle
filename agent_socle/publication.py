"""
Statut de publication des analyses (lecture), extrait tel quel de tools/analysis_publication.py d'agent-scrum-master :
brouillon local '<TICKET>-cadrage.md' (dossier courant) comparé à l'empreinte de la version publiée
(.tmp/publication de AGENT_DATA_DIR). La publication elle-même reste dans l'agent Lancement.
"""
import hashlib
import json
import os
from datetime import datetime

from agent_socle.chemins import DATA_DIR


PUBLICATION_DIR = os.path.join(DATA_DIR, ".tmp", "publication")


def cadrage_path(issue_key: str) -> str:
    return f"{issue_key}-cadrage.md"


def _fingerprint(text: str) -> str:
    return hashlib.sha256((text or "").strip().replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _record_path(issue_key: str) -> str:
    return os.path.join(PUBLICATION_DIR, f"{issue_key}.json")


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def load_record(issue_key: str) -> dict:
    try:
        with open(_record_path(issue_key), "r", encoding="utf-8") as f:
            record = json.load(f)
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return {}


def status(issue_key: str, text: str = None) -> dict:
    """
    État de l'analyse : {"publiee": bool, "publiee_le": date de la dernière publication ou "", "libelle": texte,
    "message": forme de la publication (résumé + commentaires) ou ""}. `text` : analyse à évaluer (par défaut le
    fichier '<TICKET>-cadrage.md').
    """
    text = _read(cadrage_path(issue_key)) if text is None else text
    record = load_record(issue_key)
    published_at = record.get("publiee_le", "")
    published = bool(text.strip()) and record.get("empreinte") == _fingerprint(text)
    date_label = published_at.replace("T", " à ") if published_at else ""
    if published:
        label = f"Publiée dans Jira le {date_label}"
        if record.get("message"):
            label += f" — {record['message']}"
    elif published_at:
        label = f"Analyse non publiée (brouillon) : révisée depuis sa publication du {date_label}"
    else:
        label = "Analyse non publiée (brouillon)"
    return {"publiee": published, "publiee_le": published_at, "libelle": label,
            "message": record.get("message", "") if published else ""}


def record_publication(issue_key: str, text: str, when: datetime = None, **details) -> dict:
    """Mémorise que `text` est la version publiée dans Jira (date, empreinte et forme de la publication)."""
    record = {"empreinte": _fingerprint(text),
              "publiee_le": (when or datetime.now()).isoformat(timespec="minutes"), **details}
    os.makedirs(PUBLICATION_DIR, exist_ok=True)
    with open(_record_path(issue_key), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record
