"""Réglages Cucumber par défaut (page Configuration) et lecture du verrou de génération."""
import json
import os

from agent_socle import reglages, verrou


def test_reglages_par_defaut(monkeypatch):
    assert reglages.DEFAULT_COMPILE_CMD and 0 < reglages.DEFAULT_DUP_THRESHOLD < 1
    monkeypatch.setenv("CUCUMBER_AGENT_JENKINS", "0")
    assert reglages.agent_runs_tests() is False
    monkeypatch.setenv("CUCUMBER_AGENT_JENKINS", "")
    monkeypatch.setenv("JENKINS_USER", "u")
    monkeypatch.setenv("JENKINS_API_TOKEN", "t")
    assert reglages.agent_runs_tests() is True


def test_verrou_libre_ou_tenu(tmp_path, monkeypatch):
    monkeypatch.setattr(verrou, "CUCUMBER_CACHE", str(tmp_path))
    assert verrou.holder("acme") == {}
    (tmp_path / "acme").mkdir()
    (tmp_path / "acme" / verrou.LOCK_NAME).write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    assert verrou.holder("acme")["pid"] == os.getpid()
    assert "génération en cours" in verrou.describe(verrou.holder("acme"))
