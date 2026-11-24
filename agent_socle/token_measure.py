"""
Mesure du contexte des appels Claude (0 token) : où partent les jetons.

Le coût d'un appel tient surtout à la relecture du contexte à chaque tour (cache lu) : prompt de départ, puis tout
ce que les outils ont renvoyé (fichiers lus, résultats de requêtes en base, logs…). Ce module mesure :

- le contexte moyen relu par tour : (entrée + cache écrit + cache lu) / tours ;
- le volume des résultats d'outils de l'appel, par outil (Bash classé par usage : base, logs, compilation, git,
  Jira), lu dans la transcription de la session écrite par Claude Code
  (<CLAUDE_CONFIG_DIR ou ~/.claude>/projects/*/<session>.jsonl). Une session reprise (--resume) continue le même
  fichier : seules les lignes nouvelles depuis la dernière mesure sont comptées (.tmp/token_transcripts.json).

Tout est au mieux : transcription absente ou illisible = mesure vide, jamais d'erreur pour l'étape.
"""
from agent_socle.chemins import DATA_DIR
import glob
import json
import os
import re

WORKSPACE_DIR = DATA_DIR
OFFSETS_FILE = os.path.join(WORKSPACE_DIR, ".tmp", "token_transcripts.json")
OFFSETS_MAX = 500          # sessions mémorisées au plus

_BASH = (("base", re.compile(r"db_tools|psql|sqlcmd|\bselect\b", re.I)),
         ("logs", re.compile(r"groundcover|logs?_|kubectl\s+logs", re.I)),
         ("jira", re.compile(r"jira", re.I)),
         ("compilation", re.compile(r"\bmvn\b|\bgradle|javac|compile", re.I)),
         ("git", re.compile(r"\bgit\b", re.I)))


def context_per_turn(usage: dict) -> int:
    """Jetons de contexte relus en moyenne à chaque tour de l'appel (0 si inconnu)."""
    try:
        total = sum(int(usage.get(k) or 0) for k in ("tokens_entree", "cache_ecrit", "cache_lu"))
        turns = int(usage.get("tours") or 0)
    except (TypeError, ValueError):
        return 0
    return round(total / turns) if turns > 0 else 0


def is_resumed(usage: dict) -> bool:
    """Appel qui reprend une session : cumul inconnu, ou cumul de la session supérieur au coût de l'appel."""
    if usage.get("cout_cumul_inconnu"):
        return True
    try:
        return float(usage.get("cout_session") or 0) > float(usage.get("cout_usd") or 0) + 1e-6
    except (TypeError, ValueError):
        return False


def tool_label(name: str, tool_input) -> str:
    """Nom d'outil pour la mesure : Bash détaillé par usage (Bash·base, Bash·logs…), MCP sans préfixe de serveur."""
    if name == "Bash":
        command = str((tool_input or {}).get("command", "")) if isinstance(tool_input, dict) else ""
        return next((f"Bash·{label}" for label, motif in _BASH if motif.search(command)), "Bash")
    if name.startswith("mcp__"):
        return "MCP·" + name.split("__")[-1]
    return name or "?"


def _text_size(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_text_size(c.get("text", "") if isinstance(c, dict) else c) for c in content)
    if isinstance(content, dict):
        return _text_size(content.get("text", ""))
    return 0


def transcript_path(session_id: str, config_dir: str = "") -> str:
    """Transcription de la session (dossier du compte Claude utilisé) ; '' si introuvable."""
    if not session_id or not re.fullmatch(r"[\w-]+", session_id):
        return ""
    base = os.path.expanduser(config_dir or os.environ.get("CLAUDE_CONFIG_DIR", "").strip() or "~/.claude")
    matches = glob.glob(os.path.join(base, "projects", "*", f"{session_id}.jsonl"))
    return max(matches, key=os.path.getmtime) if matches else ""


def _offsets() -> dict:
    try:
        with open(OFFSETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_offset(session_id: str, lines: int) -> None:
    data = _offsets()
    data.pop(session_id, None)
    data[session_id] = lines
    data = dict(list(data.items())[-OFFSETS_MAX:])
    try:
        os.makedirs(os.path.dirname(OFFSETS_FILE), exist_ok=True)
        with open(OFFSETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def tool_stats(session_id: str, config_dir: str = "") -> dict:
    """
    Résultats d'outils de l'appel qui vient de se terminer : {"appels", "car", "detail": {outil: [appels, car]},
    "plus_gros": [outil, car]} ; {} si la transcription est introuvable.
    """
    path = transcript_path(session_id, config_dir)
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    start = int(_offsets().get(session_id) or 0)
    start = start if start <= len(lines) else 0
    names, detail, biggest = {}, {}, ["", 0]
    for line in lines[start:]:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = ((entry.get("message") or {}).get("content")) if isinstance(entry, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[block.get("id", "")] = tool_label(block.get("name", ""), block.get("input"))
            elif block.get("type") == "tool_result":
                label = names.get(block.get("tool_use_id", ""), "?")
                size = _text_size(block.get("content"))
                calls, chars = detail.get(label, [0, 0])
                detail[label] = [calls + 1, chars + size]
                if size > biggest[1]:
                    biggest = [label, size]
    _save_offset(session_id, len(lines))
    return {"appels": sum(v[0] for v in detail.values()), "car": sum(v[1] for v in detail.values()),
            "detail": dict(sorted(detail.items(), key=lambda kv: -kv[1][1])), "plus_gros": biggest}


def detail_text(stats: dict, limit: int = 6) -> str:
    """« Read 12×48k, Bash·base 9×31k… » : les outils qui ont renvoyé le plus de texte."""
    parts = [f"{name} {calls}×{round(chars / 1000)}k" for name, (calls, chars) in
             list((stats or {}).get("detail", {}).items())[:limit]]
    return ", ".join(parts)
