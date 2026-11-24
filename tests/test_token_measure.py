"""Mesure du contexte des appels Claude (tools/token_measure.py, tools/token_report.py, main.report_token_usage)."""
import csv
import importlib
import io
import json
import os
import sys

from agent_socle import token_measure, token_report


def _main():
    """main reconfigure sys.stdout à l'import : importé sous des flux temporaires (comme test_cucumber_import)."""
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        return importlib.import_module("main")
    finally:
        sys.stdout, sys.stderr = saved


def _transcript(base, session, entries):
    folder = os.path.join(base, "projects", "projet")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{session}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


def _use(id_, name, command=""):
    return {"message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": id_, "name": name, "input": {"command": command} if command else {}}]}}


def _result(id_, text):
    return {"message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": id_, "content": [{"type": "text", "text": text}]}]}}


def test_context_per_turn():
    assert token_measure.context_per_turn({"tokens_entree": 10, "cache_ecrit": 90, "cache_lu": 900, "tours": 10}) == 100
    assert token_measure.context_per_turn({"tours": 0}) == 0
    assert token_measure.context_per_turn({"tours": "x"}) == 0


def test_tool_label():
    assert token_measure.tool_label("Bash", {"command": "python tools/db_tools.py --query x"}) == "Bash·base"
    assert token_measure.tool_label("Bash", {"command": "mvn -q compile"}) == "Bash·compilation"
    assert token_measure.tool_label("Bash", {"command": "git diff"}) == "Bash·git"
    assert token_measure.tool_label("Bash", {"command": "ls"}) == "Bash"
    assert token_measure.tool_label("mcp__odatio__base_requete", {}) == "MCP·base_requete"
    assert token_measure.tool_label("Read", {}) == "Read"


def test_is_resumed():
    assert not token_measure.is_resumed({"cout_usd": 1.0, "cout_session": 1.0})
    assert token_measure.is_resumed({"cout_usd": 0.4, "cout_session": 1.4})
    assert token_measure.is_resumed({"cout_usd": 3.0, "cout_cumul_inconnu": True})
    assert not token_measure.is_resumed({})


def test_tool_stats_counts_only_new_lines_of_resumed_session(tmp_path, monkeypatch):
    monkeypatch.setattr(token_measure, "OFFSETS_FILE", str(tmp_path / "offsets.json"))
    base = str(tmp_path / "claude")
    _transcript(base, "s1", [_use("a", "Read"), _result("a", "x" * 3000),
                             _use("b", "Bash", "python tools/db_tools.py"), _result("b", "y" * 1000)])
    stats = token_measure.tool_stats("s1", base)
    assert stats["appels"] == 2 and stats["car"] == 4000
    assert stats["detail"] == {"Read": [1, 3000], "Bash·base": [1, 1000]}
    assert stats["plus_gros"] == ["Read", 3000]
    assert "Read 1×3k" in token_measure.detail_text(stats)
    # Reprise de la même session : seul le nouvel appel est compté
    _transcript(base, "s1", [_use("c", "Grep"), _result("c", "z" * 500)])
    stats = token_measure.tool_stats("s1", base)
    assert stats["detail"] == {"Grep": [1, 500]}


def test_tool_stats_without_transcript(tmp_path):
    assert token_measure.tool_stats("inconnue", str(tmp_path)) == {}
    assert token_measure.tool_stats("../evil", str(tmp_path)) == {}
    assert token_measure.tool_stats("", str(tmp_path)) == {}


def test_report_token_usage_migrates_old_csv_and_adds_columns(tmp_path, monkeypatch, capsys):
    main = _main()
    csv_file = tmp_path / "token_usage.csv"
    old = ["date", "ticket", "etape", "modele", "effort", "tokens_entree", "cache_ecrit", "cache_lu", "tokens_sortie",
           "tours", "duree_s", "cout_usd", "taille_prompt", "code_retour"]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=old, delimiter=";")
        w.writeheader()
        w.writerow({k: "" for k in old} | {"ticket": "ODA-1", "cout_usd": "0.5"})
    monkeypatch.setattr(main, "TOKEN_USAGE_CSV", str(csv_file))
    monkeypatch.setattr(token_measure, "tool_stats", lambda sid: {
        "appels": 3, "car": 12000, "detail": {"Read": [2, 10000], "Bash·base": [1, 2000]}, "plus_gros": ["Read", 9000]})
    usage = {"tokens_entree": 100, "cache_ecrit": 900, "cache_lu": 9000, "tokens_sortie": 50, "tours": 10,
             "duree_s": 12, "cout_usd": 0.4, "cout_session": 1.4, "session_id": "s1"}
    main.report_token_usage("ODA-2", "cucumber-fix", "haiku", usage, 1234, 0)
    out = capsys.readouterr().out
    assert "contexte/tour=1k" in out and "reprise=oui" in out and "[CONTEXTE]" in out
    with open(csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert rows[0]["ticket"] == "ODA-1" and rows[0]["reprise"] == ""
    assert rows[1]["reprise"] == "oui" and rows[1]["contexte_tour"] == "1000" and rows[1]["session"] == "s1"
    assert json.loads(rows[1]["outils_detail"]) == {"Read": [2, 10000], "Bash·base": [1, 2000]}


def test_report_token_usage_survives_measure_failure(tmp_path, monkeypatch):
    main = _main()
    monkeypatch.setattr(main, "TOKEN_USAGE_CSV", str(tmp_path / "t.csv"))

    def boom(_):
        raise RuntimeError("transcription illisible")
    monkeypatch.setattr(token_measure, "tool_stats", boom)
    main.report_token_usage("ODA-3", "cucumber-lot", "", {"tokens_entree": 1, "cache_ecrit": 0, "cache_lu": 0,
                                                          "tokens_sortie": 1, "tours": 1, "duree_s": 1,
                                                          "cout_usd": 0.1}, 10, 0)
    assert (tmp_path / "t.csv").exists()


def test_token_report(tmp_path):
    main = _main()
    csv_file = tmp_path / "t.csv"
    fields = main.TOKEN_USAGE_FIELDS
    rows = [
        {"date": "2026-11-18T10:00:00", "ticket": "ODA-1", "etape": "cucumber-lot", "cout_usd": "3", "tours": "20",
         "contexte_tour": "80000", "reprise": "non", "outils_detail": json.dumps({"Read": [5, 50000]})},
        {"date": "2026-11-19T10:00:00", "ticket": "ODA-1", "etape": "cucumber-fix", "cout_usd": "1", "tours": "10",
         "contexte_tour": "200000", "reprise": "oui", "outils_detail": json.dumps({"Read": [1, 1000],
                                                                                   "Bash·base": [4, 20000]})},
        {"date": "2026-11-19T11:00:00", "ticket": "ODA-2", "etape": "cadrage", "cout_usd": "0,5"},
    ]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";", restval="")
        w.writeheader()
        w.writerows(rows)
    summary = token_report.summarize(token_report.read_rows(str(csv_file)))
    assert summary["total"] == 4.5 and list(summary["etapes"])[0] == "cucumber-lot"
    assert summary["etapes"]["cucumber-lot"]["part"] == 66.7
    assert summary["etapes"]["cucumber-fix"]["reprises"] == 1
    assert summary["outils"] == {"Read": [6, 51000], "Bash·base": [4, 20000]}
    assert len(token_report.read_rows(str(csv_file), since="2026-11-19")) == 2
    assert len(token_report.read_rows(str(csv_file), ticket="oda-1", step="cucumber")) == 2
    text = token_report.render(summary)
    assert "cucumber-lot" in text and "Bash·base" in text
    assert token_report.main(["--fichier", str(csv_file), "--ticket", "ODA-9"]) == 1
