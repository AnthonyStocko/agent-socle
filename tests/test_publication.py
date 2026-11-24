"""Statut de publication (lecture) : brouillon, publiée, révisée depuis la publication."""
import json

from agent_socle import besoin, publication


def test_statut_suit_l_empreinte(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(publication, "PUBLICATION_DIR", str(tmp_path / "publication"))
    assert publication.status("PROJ-1")["libelle"] == "Analyse non publiée (brouillon)"
    (tmp_path / publication.cadrage_path("PROJ-1")).write_text("# Cadrage\nV1", encoding="utf-8")
    (tmp_path / "publication").mkdir()
    (tmp_path / "publication" / "PROJ-1.json").write_text(json.dumps(
        {"empreinte": publication._fingerprint("# Cadrage\nV1"), "publiee_le": "2026-11-04T09:30"}), encoding="utf-8")
    assert publication.status("PROJ-1")["libelle"] == "Publiée dans Jira le 2026-11-04 à 09:30"
    assert not publication.status("PROJ-1", "# Cadrage\nV2")["publiee"]
    assert besoin.SECTION_TITLE == "Intégration du besoin"
