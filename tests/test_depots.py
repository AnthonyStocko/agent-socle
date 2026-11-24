"""Dépôts et versions communs aux étapes : normalisation, références du Standard, poussée désactivée."""
from agent_socle import depots, versions


def test_versions_et_references():
    assert versions.normalize("26.16") == versions.normalize("26.16.0") or versions.normalize("26.16")
    assert list(versions.std_refs("", ("HEAD",)))
    assert depots.ODATIO_VERSION.match("26.16") and not depots.ODATIO_VERSION.match("x")
    assert depots.STD_REF_LOG.startswith("[CUCUMBER STD]")
    assert depots.BACKUP_DIR.endswith("sauvegardes")


def test_poussee_desactivee(repo):
    depots.disable_push(repo)
    import subprocess
    url = subprocess.run(["git", "-C", repo, "remote", "get-url", "--push", "origin"], capture_output=True, text=True)
    assert depots.READ_ONLY_PUSH_URL in url.stdout or url.returncode != 0
