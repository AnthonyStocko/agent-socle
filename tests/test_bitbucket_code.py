import argparse
import subprocess

from agent_socle import bitbucket_code as bc


class FakeStd:
    project, base, token = "COMPONENT", "https://git.example", ""

    def __init__(self):
        self.files_by = {"wms-content-backend": ["a/Action.java", "a/README.md", "b/Other.java"]}
        self.text = {"a/Action.java": "class Action {\n  void batch() {}\n}\n", "b/Other.java": "x\n"}

    def repos(self):
        return sorted(self.files_by)

    def ref(self, repo, candidates):
        assert candidates[:2] == ["origin/dev", "origin/development"] and candidates[-1] == "HEAD"
        return "abc1234567890"

    def ref_name(self, repo, commit):
        return "development"

    def files(self, repo, ref):
        return self.files_by[repo]

    def show(self, repo, ref, path):
        return self.text.get(path, "")

    def search(self, query):
        return [("wms-content-backend", "a/Action.java")]


def ns(**kw):
    return argparse.Namespace(**kw)


def test_reads_the_latest_commit_of_the_base_branch(monkeypatch):
    monkeypatch.delenv("STD_BASE_BRANCHES", raising=False)
    std = FakeStd()
    assert bc.cmd_repos(std, ns(like="content")) == ["wms-content-backend"]
    assert bc.cmd_search(std, ns(query="batch", limit=5)) == ["wms-content-backend/a/Action.java"]
    files = bc.cmd_files(std, ns(repo="wms-content-backend", prefix="a/", like="", max=300))
    assert "@ development (abc1234567)" in files[0] and files[1:] == ["a/Action.java", "a/README.md"]
    shown = bc.cmd_show(std, ns(repo="wms-content-backend", path="a/Action.java", start=2, end=2))
    assert shown[1] == "2\t  void batch() {}"
    grep = bc.cmd_grep(std, ns(repo="wms-content-backend", regex=r"batch\(", prefix="", ext=".java",
                                max_files=300, max=100))
    assert grep[1] == "a/Action.java:2: void batch() {}"


def test_unknown_repo_is_an_error():
    try:
        bc.cmd_files(FakeStd(), ns(repo="absent", prefix="", like="", max=10))
        raise AssertionError("erreur attendue")
    except bc.BitbucketUnavailable as e:
        assert "absent" in str(e)


def test_checkout_clones_only_the_modified_repo_without_credentials(monkeypatch, tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "development", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    (seed / "f.txt").write_text("v1\n")
    for args in (["add", "f.txt"], ["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "v1"],
                 ["push", "-q", "origin", "HEAD:development"]):
        subprocess.run(["git", *args], cwd=seed, check=True)
    std = FakeStd()
    std.files_by["origin"] = []
    monkeypatch.setattr(bc, "ROOT", str(tmp_path / "ws"))
    real_git = bc._git
    monkeypatch.setattr(bc, "_git", lambda args, cwd=None, token="": real_git(
        [str(origin) if a.endswith("/origin.git") else a for a in args], cwd, token))
    out = bc.cmd_checkout(std, ns(repo="origin"))
    target = tmp_path / "ws" / ".tmp" / "std_COMPONENT_travail" / "origin"
    assert str(target) in out[0] and "development" in out[1] and (target / "f.txt").read_text() == "v1\n"
    config = subprocess.run(["git", "config", "--list"], cwd=target, capture_output=True, text=True).stdout
    assert "extraheader" not in config.lower()
    (seed / "f.txt").write_text("v2\n")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qam", "v2"], cwd=seed, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:development"], cwd=seed, check=True)
    bc.cmd_checkout(std, ns(repo="origin"))
    assert (target / "f.txt").read_text() == "v2\n"


def test_default_candidates_are_unchanged_without_branches(monkeypatch):
    monkeypatch.delenv("STD_BASE_BRANCHES", raising=False)
    assert bc.base_candidates() == ["origin/dev", "origin/development", "HEAD"]
    assert bc.base_candidates("") == bc.base_candidates()


class RecordingStd(FakeStd):
    def __init__(self):
        super().__init__()
        self.files_by["clix-tools"] = ["t/Tool.java"]
        self.seen = []

    def ref(self, repo, candidates):
        self.seen.append(list(candidates))
        return "def4567890123"

    def search(self, query):
        return [("clix-tools", "t/Tool.java"), ("wms-content-backend", "a/Action.java")]


def test_branches_option_is_passed_as_is_to_the_reader():
    std = RecordingStd()
    bc.cmd_files(std, ns(repo="clix-tools", prefix="", like="", max=10, branches="origin/integration", repos=""))
    assert std.seen == [["origin/integration"]]
    bc.cmd_show(std, ns(repo="clix-tools", path="t/Tool.java", start=1, end=0,
                        branches="origin/release/26.24,v26.24,HEAD", repos=""))
    assert std.seen[-1] == ["origin/release/26.24", "v26.24", "HEAD"]


def test_repos_option_limits_the_readable_repositories():
    std = RecordingStd()
    assert bc.cmd_repos(std, ns(like="", repos="clix-tools")) == ["clix-tools"]
    assert bc.cmd_search(std, ns(query="Tool", limit=5, repos="clix-tools")) == ["clix-tools/t/Tool.java"]
    try:
        bc.cmd_files(std, ns(repo="wms-content-backend", prefix="", like="", max=10, branches="", repos="clix-tools"))
        raise AssertionError("erreur attendue")
    except bc.BitbucketUnavailable as e:
        assert "hors du périmètre" in str(e)


def test_main_reads_global_options(monkeypatch, capsys):
    std = RecordingStd()
    monkeypatch.setattr(bc, "standard", lambda project: std)
    assert bc.main(["--project", "CLIX", "--branches", "origin/integration", "--repos", "clix-tools",
                    "files", "clix-tools"]) == 0
    assert std.seen == [["origin/integration"]] and "t/Tool.java" in capsys.readouterr().out
    assert bc.main(["--repos", "clix-tools", "files", "wms-content-backend"]) == 1
    assert "BITBUCKET_ERROR=" in capsys.readouterr().out


BASE = "https://git.example"


def test_client_source_from_urls():
    assert bc.client_source(f"{BASE}/projects/CLIX", BASE) == ("CLIX", None)
    assert bc.client_source(f"{BASE}/projects/CLIX/", BASE) == ("CLIX", None)
    assert bc.client_source(f"{BASE}/projects/CLIX/repos/clix-app/browse", BASE) == ("CLIX", ["clix-app"])
    assert bc.client_source(f"{BASE}/scm/clix/clix-app.git", BASE) == ("CLIX", ["clix-app"])
    assert bc.client_source("ssh://git@git.example:7999/clix/clix-app.git", BASE) == ("CLIX", ["clix-app"])
    assert bc.client_source("https://other.example/scm/clix/clix-app.git", BASE) == ("", None)
    assert bc.client_source("", BASE) == ("", None)
    assert bc.client_source("STD_ONLY", BASE) == ("", None)


def _clone(path, remote=""):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if remote:
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)
    return path


def test_client_source_from_a_local_clone(tmp_path):
    clone = _clone(tmp_path / "clix-app", f"{BASE}/scm/clix/clix-app.git")
    assert bc.client_source(str(clone), BASE) == ("CLIX", ["clix-app"])


def test_client_source_from_a_folder_of_clones(tmp_path):
    _clone(tmp_path / "CLIX" / "clix-app", f"{BASE}/scm/clix/clix-app.git")
    _clone(tmp_path / "CLIX" / "clix-ui", f"{BASE}/scm/clix/clix-ui.git")
    (tmp_path / "CLIX" / "notes").mkdir()
    assert bc.client_source(str(tmp_path / "CLIX"), BASE) == ("CLIX", ["clix-app", "clix-ui"])


def test_client_source_unresolved_local_folders(tmp_path):
    _clone(tmp_path / "mixed" / "clix-app", f"{BASE}/scm/clix/clix-app.git")
    _clone(tmp_path / "mixed" / "other-app", f"{BASE}/scm/othr/other-app.git")
    assert bc.client_source(str(tmp_path / "mixed"), BASE) == ("", None)
    assert bc.client_source(str(_clone(tmp_path / "no-remote")), BASE) == ("", None)
    (tmp_path / "empty").mkdir()
    assert bc.client_source(str(tmp_path / "empty"), BASE) == ("", None)


def test_prompt_block_renders():
    import importlib, io, sys
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    try:
        main = importlib.import_module("main")
    finally:
        sys.stdout, sys.stderr = saved
    text = main.render_prompt("std_bitbucket_code", cli="PY BB", work_root="/w")
    assert "PY BB grep DEPOT" in text and "PY BB checkout DEPOT" in text and "'/w'" in text
