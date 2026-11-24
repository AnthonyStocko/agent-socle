"""Socle des CLI : ordre de recherche des prompts (agent puis socle) et délégation à la CLI d'un autre agent."""
import os

import pytest

from agent_socle import cli


def test_prompt_de_l_agent_puis_du_socle(tmp_path, monkeypatch):
    monkeypatch.delenv("PROMPTS_DIR", raising=False)
    (tmp_path / "essai.md").write_text("Bonjour ${nom}", encoding="utf-8")
    (tmp_path / "token_saving_rules.md").write_text("version de l'agent", encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_PROMPTS_DIR", str(tmp_path))
    assert cli.render_prompt("essai", nom="Léa") == "Bonjour Léa"
    assert cli.render_prompt("token_saving_rules") == "version de l'agent"
    monkeypatch.setattr(cli, "DEFAULT_PROMPTS_DIR", "")
    assert cli.render_prompt("token_saving_rules") != "version de l'agent"
    with pytest.raises(SystemExit):
        cli.render_prompt("essai", nom="x")


def test_prompts_communs_presents():
    for nom in ("token_saving_rules", "odatio_docs", "db_access"):
        assert os.path.exists(os.path.join(cli.SOCLE_PROMPTS_DIR, f"{nom}.md"))


def test_delegation_avec_les_memes_arguments(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("import sys\nsys.exit(len(sys.argv[1:]))\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_REVUE_PR_DIR", str(tmp_path))
    assert cli.deleguer("revue-pr", ["--step", "review-pr", "--pr-url", "u"]) == 4
    monkeypatch.setenv("AGENT_REVUE_PR_DIR", str(tmp_path / "absent"))
    assert cli.deleguer("revue-pr", []) == 2


def test_limite_d_usage_reconnue():
    assert cli.usage_limit_hit("You've hit your session limit")
    assert cli.usage_limit_reset("You've hit your 5-hour limit · resets 7:30pm") == "resets 7:30pm"
