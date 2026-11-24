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


def test_etape_simulee_lue_comme_avant(tmp_path, monkeypatch):
    """Processus qui fournit sa sortie (simulation des tests d'IHM) : lignes lues, journaux écrits, tâche terminée."""
    from agent_socle import taches
    monkeypatch.setenv("AGENT_TACHES_DIR", str(tmp_path / "taches"))
    monkeypatch.setenv("AGENT_RUN_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AGENT_JOURNAL_PATH", str(tmp_path / "tech.log"))

    class Simule:
        pid = 0
        stdout = iter(["[CUCUMBER] début\n", "[CUCUMBER] ❌ échec\n"])

        def wait(self):
            return 3
    monkeypatch.setattr(taches.subprocess, "Popen", lambda cmd, **k: Simule())
    monkeypatch.setattr(st, "session_state", {})
    vus = []
    assert ihm.run_main_step(["py", "main.py", "--step", "generate-cucumber-client"], on_line=vus.append) == 3
    assert vus == ["[CUCUMBER] début\n", "[CUCUMBER] ❌ échec\n"] and ihm.journal_phrases("[CUCUMBER]")[1] == "❌ échec"
    tache = taches.lister()[0]
    assert (tache["statut"], tache["code_retour"]) == ("echec", 3)
    assert "[CUCUMBER] début" in open(tache["journal"], encoding="utf-8").read()


def test_etape_detachee_suivie_par_son_journal(tmp_path, monkeypatch):
    """Relais détaché réel (commande inoffensive) : la page suit le journal, comme après une reconnexion."""
    import sys
    from agent_socle import taches
    monkeypatch.setenv("AGENT_TACHES_DIR", str(tmp_path / "taches"))
    monkeypatch.setenv("AGENT_RUN_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AGENT_JOURNAL_PATH", str(tmp_path / "tech.log"))
    monkeypatch.setattr(st, "session_state", {})
    monkeypatch.setattr(ihm, "AGENT", "essai")
    vus = []
    code = ihm.run_main_step([sys.executable, "-c", "print('un'); print('deux')"], on_line=vus.append)
    assert code == 0 and [v.strip() for v in vus] == ["un", "deux"]
    assert taches.lister("essai")[0]["statut"] == "terminee"
