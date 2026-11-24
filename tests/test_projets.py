"""Registre des projets (façade en lecture) et client de l'API d'agent-projets."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_socle import projets


def _cucumber(root, client, projet=None, inventaire=None):
    dossier = root / client
    dossier.mkdir(parents=True)
    if projet is not None:
        (dossier / "projet.json").write_text(json.dumps(projet), encoding="utf-8")
    if inventaire is not None:
        (dossier / "inventaire.json").write_text(json.dumps(inventaire), encoding="utf-8")


def _commun(dossier, texte):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "commun.toml").write_text(texte, encoding="utf-8")


def test_known_projects_lit_reglages_et_inventaire(tmp_path):
    _cucumber(tmp_path, "alpha", projet={"client_repo": "r1", "db_schema": "S"})
    _cucumber(tmp_path, "beta", inventaire={"depot_client": "r2"})
    (tmp_path / "_cache").mkdir()
    (tmp_path / "vide").mkdir()
    assert projets.known_projects(str(tmp_path)) == {"alpha": {"client_repo": "r1", "db_schema": "S"},
                                                     "beta": {"client_repo": "r2"}}


def test_applications_du_manager_sans_fichier_ni_erreur(tmp_path):
    assert projets.applications(str(tmp_path)) == {}
    _commun(tmp_path, "[[applications]\n")
    assert projets.applications(str(tmp_path)) == {}
    _commun(tmp_path, '[[applications]]\nnom = "alpha"\njira_projet = "ALP"\n[[applications]]\ndescription = "sans nom"\n')
    assert projets.applications(str(tmp_path)) == {"alpha": {"nom": "alpha", "jira_projet": "ALP"}}


def test_registre_assemble_les_deux_sources_sans_fusion(tmp_path):
    _cucumber(tmp_path / "cache", "alpha", projet={"client_repo": "r1"})
    _commun(tmp_path / "config", '[[applications]]\nnom = "alpha"\n[[applications]]\nnom = "gamma"\n')
    reg = projets.registre(str(tmp_path / "cache"), str(tmp_path / "config"))
    assert reg == {"alpha": {"cucumber": {"client_repo": "r1"}, "application": {"nom": "alpha"}},
                   "gamma": {"cucumber": None, "application": {"nom": "gamma"}}}


def test_dossier_du_manager_par_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("SAVOYE_CONFIG_DIR", str(tmp_path))
    assert projets.dossier_manager() == str(tmp_path)
    monkeypatch.delenv("SAVOYE_CONFIG_DIR")
    assert projets.dossier_manager().endswith("config")


def test_lire_sans_api_lit_localement(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_PROJETS_API", "http://127.0.0.1:9")   # port fermé
    monkeypatch.setattr(projets, "registre", lambda: {"alpha": {"cucumber": {}, "application": None}})
    assert projets.lire("/projets", delai=0.5) == {"alpha": {"cucumber": {}, "application": None}}
    assert projets.lire("/projets/alpha", delai=0.5) == {"cucumber": {}, "application": None}
    assert projets.lire("/projets/inconnu", delai=0.5) is None
    assert projets.lire("/sante", delai=0.5)["source"] == "locale"


def test_lire_interroge_l_api(monkeypatch):
    class Reponse(BaseHTTPRequestHandler):
        def do_GET(self):
            corps = json.dumps({"chemin": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *args):
            pass

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Reponse)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("AGENT_PROJETS_API", f"http://127.0.0.1:{serveur.server_port}/")
        assert projets.lire("/projets/alpha") == {"chemin": "/projets/alpha"}
    finally:
        serveur.shutdown()
