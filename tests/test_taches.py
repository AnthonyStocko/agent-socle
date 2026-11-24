"""Travaux en cours : registre, tâches interrompues, contexte de page, lancement détaché (simulé puis réel, inoffensif)."""
import os
import subprocess
import sys
import time

import pytest

from agent_socle import taches


@pytest.fixture(autouse=True)
def dossiers(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_TACHES_DIR", str(tmp_path / "taches"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    return tmp_path


class FauxProcessus:
    pid = 0
    stdout = None


def test_lancement_detache_et_registre(tmp_path, monkeypatch):
    lances = []
    monkeypatch.setattr(taches.subprocess, "Popen", lambda cmd, **k: lances.append((cmd, k)) or FauxProcessus())
    cmd = [sys.executable, "main.py", "--step", "cadrage", "--issue", "ODA-12", "--project", "ODA"]
    _, tache = taches.lancer("lancement", cmd, str(tmp_path / "j.log"), str(tmp_path / "t.log"), auteur="lea",
                             contexte={"jira_tickets": ["ODA-12"]})
    relais, options = lances[0]
    assert relais[1:5] == ["-m", "agent_socle.taches", "lancement", tache["id"]] and relais[5] == "--"
    assert relais[6:] == cmd and options["stdout"] == subprocess.DEVNULL       # jamais de tube vers la page
    if os.name == "nt":
        assert options["creationflags"] & subprocess.DETACHED_PROCESS
        assert options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    lu = taches.lire("lancement", tache["id"])
    assert (lu["etape"], lu["cible"], lu["auteur"], lu["statut"]) == ("cadrage", "ODA-12", "lea", "en_cours")
    assert lu["contexte"] == {"jira_tickets": ["ODA-12"]} and lu["journal"].endswith("j.log")


def test_tache_sans_processus_interrompue_au_demarrage(tmp_path, monkeypatch):
    monkeypatch.setattr(taches.subprocess, "Popen", lambda cmd, **k: FauxProcessus())
    _, tache = taches.lancer("cucumber", [sys.executable, "main.py", "--step", "generate-cucumber-client",
                                          "--client-name", "acme"], str(tmp_path / "j.log"), str(tmp_path / "t.log"))
    liste = taches.lister("cucumber")
    assert [t["statut"] for t in liste] == ["interrompue"] and liste[0]["cible"] == "acme" and liste[0]["fin"]


def test_les_miennes_d_abord(tmp_path, monkeypatch):
    monkeypatch.setattr(taches.subprocess, "Popen", lambda cmd, **k: FauxProcessus())
    for qui in ("tom", "lea", "tom"):
        taches.lancer("revue-pr", [sys.executable, "main.py", "--step", "review-pr"], str(tmp_path / f"{qui}.log"),
                      str(tmp_path / "t.log"), auteur=qui)
    assert [t["auteur"] for t in taches.lister("revue-pr", "lea")][0] == "lea"
    assert len(taches.lister()) == 3


def test_contexte_enregistre_puis_recharge():
    taches.enregistrer_contexte("lea@x", "cucumber", {"cs_project": "acme", "objet": object(), "lots": [1, 2]})
    assert taches.charger_contexte("lea@x", "cucumber") == {"cs_project": "acme", "lots": [1, 2]}
    assert taches.charger_contexte("tom", "cucumber") == {}


def test_relais_reel_ecrit_les_journaux_et_termine(tmp_path):
    """Relais détaché réel sur une commande inoffensive : journaux écrits, statut et code retour enregistrés."""
    script = "import time\nfor i in range(3):\n    print(f'ligne {i}', flush=True)\n    time.sleep(0.2)\n"
    cmd = [sys.executable, "-c", script]
    process, tache = taches.lancer("essai", cmd, str(tmp_path / "logs" / "run.log"), str(tmp_path / "tech.log"))
    limite = time.time() + 60
    while taches.lire("essai", tache["id"])["statut"] == "en_cours" and time.time() < limite:
        time.sleep(0.2)
    fin = taches.lire("essai", tache["id"])
    assert (fin["statut"], fin["code_retour"]) == ("terminee", 0)
    journal = open(fin["journal"], encoding="utf-8").read()
    assert "ligne 0" in journal and "ligne 2" in journal and "code retour 0" in journal
    assert "ligne 2" in open(tmp_path / "tech.log", encoding="utf-8").read()


def test_arret_d_une_tache(tmp_path):
    cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    _, tache = taches.lancer("essai", cmd, str(tmp_path / "run.log"), str(tmp_path / "tech.log"))
    time.sleep(1)
    assert taches.arreter("essai", tache["id"])["statut"] == "arretee"
    limite = time.time() + 20
    while taches.vivante(taches.lire("essai", tache["id"])) and time.time() < limite:
        time.sleep(0.2)
    assert not taches.vivante(taches.lire("essai", tache["id"]))
    assert taches.lire("essai", tache["id"])["statut"] == "arretee"      # le relais tué ne réécrit pas le statut
