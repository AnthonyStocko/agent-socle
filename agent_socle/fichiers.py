"""Lecture JSON tolérante (extraite de tools/cucumber_tools.py, inchangée)."""
import json


def _read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default
