"""Socle des IHM : chemins des journaux lus à chaque appel, phrases et cause d'interruption."""
import os

import streamlit as st

from agent_socle import chemins, ihm


def test_journaux_suivent_l_environnement(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_JOURNAL_PATH", raising=False)
    monkeypatch.delenv("AGENT_RUN_LOGS_DIR", raising=False)
    assert ihm.journal_path() == os.path.join(chemins.DATA_DIR, ".tmp", "journal_technique.log")
    monkeypatch.setenv("AGENT_RUN_LOGS_DIR", str(tmp_path))
    assert ihm.run_log_path(["python", "main.py", "--step", "review-pr"]).startswith(str(tmp_path))
    assert ihm.run_log_path(["python", "main.py", "--step", "review-pr"]).endswith("_review-pr.log")


def test_cause_d_interruption(monkeypatch):
    monkeypatch.setattr(st, "session_state", {"last_run_lines": ["[REVUE PR] ❌ Aucune pull request à relire."]})
    assert ihm.interruption_cause(2) == "Aucune pull request à relire."
    monkeypatch.setattr(st, "session_state", {"last_run_lines": [f"{ihm.CUCUMBER_ENV_PREFIX} base absente"]})
    assert ihm.journal_phrases(ihm.CUCUMBER_ENV_PREFIX) == ["base absente"]
