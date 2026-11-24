"""Registre local des livraisons de patchs (tools/livraisons.py), écrit par l'étape patch. Données fictives."""
import json
import os
from datetime import datetime, timedelta

import pytest

from agent_socle import livraisons


@pytest.fixture
def registre(tmp_path):
    return str(tmp_path / ".tmp" / "livraisons.jsonl")


def test_noter_et_lire(registre):
    hier = datetime.now() - timedelta(days=1)
    assert livraisons.noter("oda-1", ["ODA-1-std.patch", "ODA-1-client-x.patch"], {"ODA-1-std.patch"},
                            quand=hier, chemin=registre)
    assert livraisons.noter("ODA-2", ["ODA-2-std.patch"], {"ODA-2-std.patch", "autre.txt"}, chemin=registre)
    lues = livraisons.lire(7, registre)
    assert [l["ticket"] for l in lues] == ["ODA-2", "ODA-1"]               # plus récente d'abord
    assert lues[1] == {"ticket": "ODA-1", "date": hier.isoformat(timespec="seconds"),
                       "fichiers": ["ODA-1-std.patch", "ODA-1-client-x.patch"],
                       "pieces_jointes": ["ODA-1-std.patch"], "verification": "ok"}
    assert lues[0]["pieces_jointes"] == ["ODA-2-std.patch"]                 # pièces jointes étrangères ignorées


def test_seuls_les_noms_de_fichiers_sont_gardes(registre):
    livraisons.noter("ODA-3", [os.path.join("C:\\", "poste", "ODA-3-std.patch"), "notes.md", "../x.patch"], [],
                     chemin=registre)
    ligne = json.loads(open(registre, encoding="utf-8").read())
    assert ligne["fichiers"] == ["ODA-3-std.patch", "x.patch"]
    assert "poste" not in json.dumps(ligne)


def test_entrees_invalides_refusees(registre):
    assert not livraisons.noter("pas une clé", ["ODA-1-std.patch"], [], chemin=registre)
    assert not livraisons.noter("ODA-1", [], [], chemin=registre)
    assert not livraisons.noter("ODA-1", ["notes.md"], [], chemin=registre)
    assert not os.path.exists(registre)


def test_fenetre_et_lignes_illisibles(registre):
    livraisons.noter("ODA-1", ["ODA-1-std.patch"], [], quand=datetime.now() - timedelta(days=40), chemin=registre)
    livraisons.noter("ODA-2", ["ODA-2-std.patch"], [], chemin=registre)
    with open(registre, "a", encoding="utf-8") as f:
        f.write("pas du json\n" + json.dumps({"ticket": "../x", "date": "2099-01-01", "fichiers": ["a.patch"]}) + "\n")
    assert [l["ticket"] for l in livraisons.lire(7, registre)] == ["ODA-2"]
    assert [l["ticket"] for l in livraisons.lire(60, registre)] == ["ODA-2", "ODA-1"]


def test_registre_absent_ou_illisible(registre, tmp_path):
    assert livraisons.lire(7, registre) == []
    dossier = tmp_path / "dossier.jsonl"
    dossier.mkdir()
    with pytest.raises(livraisons.RegistreErreur):
        livraisons.lire(7, str(dossier))


def test_ecriture_au_mieux(tmp_path):
    bloquant = tmp_path / "fichier"
    bloquant.write_text("x")
    assert livraisons.noter("ODA-1", ["ODA-1-std.patch"], [], chemin=str(bloquant / "livraisons.jsonl")) is False


def test_nombre_de_lignes_borne(registre, monkeypatch):
    monkeypatch.setattr(livraisons, "LIGNES_MAX", 3)
    for i in range(5):
        livraisons.noter(f"ODA-{i}", [f"ODA-{i}-std.patch"], [], chemin=registre)
    assert [l["ticket"] for l in livraisons.lire(7, registre)] == ["ODA-4", "ODA-3", "ODA-2"]


def test_noter_patch_verifie_les_pieces_jointes_en_lecture(registre):
    lus = []

    def pieces_jointes(cle):
        lus.append(cle)
        return {"ODA-5-std.patch"}
    assert livraisons.noter_patch("oda-5", ["ODA-5-std.patch", "ODA-5-client-x.patch"], pieces_jointes,
                                  chemin=registre)
    assert lus == ["ODA-5"]
    l = livraisons.lire(7, registre)[0]
    assert (l["pieces_jointes"], l["verification"]) == (["ODA-5-std.patch"], "ok")


def test_noter_patch_jira_injoignable(registre):
    def en_panne(cle):
        raise ConnectionError("hôte interne injoignable")
    assert livraisons.noter_patch("ODA-6", ["ODA-6-std.patch"], en_panne, chemin=registre)
    l = livraisons.lire(7, registre)[0]
    assert l["pieces_jointes"] == [] and l["verification"] == "Jira illisible (ConnectionError)"
    assert "interne" not in open(registre, encoding="utf-8").read()    # aucun message d'erreur brut stocké
