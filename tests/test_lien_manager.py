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

