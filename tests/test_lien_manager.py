"""Liens préremplis d'agent-manager-savoye (tools/lien_manager.py, app.apply_manager_link)."""
import os

import pytest

from agent_socle import lien_manager as lm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ("integration", "lancement", "cucumber", "assistant")


def test_lire_valide_et_filtre():
    assert lm.lire({"page": "cucumber", "ticket": "ODA-1"}, PAGES) == {}          # pas un lien du manager
    lien = lm.lire({"source": ["manager"], "page": "cucumber", "ticket": "oda-12", "projet": "clientx",
                    "question": " Pourquoi ? ", "contexte": "Lancer\nles tests", "demande": "ignorée"}, PAGES)
    assert lien == {"page": "cucumber", "ticket": "ODA-12", "projet": "clientx", "question": "Pourquoi ?",
                    "contexte": "Lancer les tests"}
    assert lm.lire({"source": "manager", "page": "inconnue", "ticket": "pas-un ticket", "projet": "a/b"}, PAGES) == {}
    assert len(lm.lire({"source": "manager", "question": "x" * 5000}, PAGES)["question"]) == lm.TEXTE_MAX


def test_signature_projet_et_ticket():
    assert lm.signature({"b": "2", "a": "1"}) == "a=1|b=2"
    assert lm.projet_connu("Client-X", ["clientx", "autre"]) == "clientx"
    assert lm.projet_connu("inconnu", ["clientx"]) == "" and lm.projet_connu("", ["clientx"]) == ""
    assert lm.projet_jira("ODA-12") == "ODA" and lm.projet_jira("") == ""



def test_parametres_valides_et_bornes():
    p = lm.parametres(("developper",), page="developper", ticket="oda-3", depot="agent-lancement",
                      demande="d" * 5000, conversation="20260101-101010-123456", projet="a/b", contexte="x" * 900)
    assert p["source"] == "manager" and list(p)[0] == "source"
    assert p["page"] == "developper" and p["ticket"] == "ODA-3" and p["depot"] == "agent-lancement"
    assert len(p["demande"]) == lm.TEXTE_MAX and p["demande"].endswith("…")
    assert len(p["contexte"]) == lm.CONTEXTE_MAX and "projet" not in p
    assert p["conversation"] == "20260101-101010-123456"
    assert lm.parametres((), page="developper") == {}                       # page inconnue de l'agent : rien
    assert lm.parametres((), depot="a/b", ticket="pas une clé") == {}


def test_construire():
    from urllib.parse import parse_qs, urlsplit
    assert lm.construire("http://127.0.0.1:8503/") == "http://127.0.0.1:8503/"
    lien = lm.construire("http://127.0.0.1:8503/", ("developper",), page="developper", depot="agent-lancement",
                         demande="Ajouter une règle & vérifier ?")
    parties = urlsplit(lien)
    assert parties.path == "/" and {k: v[0] for k, v in parse_qs(parties.query).items()} == {
        "source": "manager", "page": "developper", "depot": "agent-lancement",
        "demande": "Ajouter une règle & vérifier ?"}
