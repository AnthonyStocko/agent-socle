"""Commandes git de l'agent (extraites de tools/cucumber_tools.py, inchangées)."""
import os
import subprocess

# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

AGENT_GIT_NAME = "Agent Cucumber"
AGENT_GIT_EMAIL = "agent-cucumber@noreply.invalid"
# Commandes Git qui créent des commits : signées de l'identité de l'agent (auteur et committer)
_COMMITTING = {"commit", "merge", "rebase", "cherry-pick", "revert", "am", "pull"}


def agent_identity() -> tuple:
    """(nom, e-mail) des commits de l'agent : distincts de ceux d'un humain (CUCUMBER_AGENT_GIT_NAME/EMAIL)."""
    return (os.getenv("CUCUMBER_AGENT_GIT_NAME", "").strip() or AGENT_GIT_NAME,
            os.getenv("CUCUMBER_AGENT_GIT_EMAIL", "").strip() or AGENT_GIT_EMAIL)


def _git(repo: str, *args, stdin: str = None) -> subprocess.CompletedProcess:
    identity = []
    if args and args[0] in _COMMITTING:
        name, email = agent_identity()
        identity = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    return subprocess.run(["git", "-C", repo, *identity, *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def git_repos(root: str) -> dict:
    """Dépôts git de `root` (lui-même ou ses sous-dossiers directs) : {nom: chemin}."""
    if not root or not os.path.isdir(root):
        return {}
    if os.path.exists(os.path.join(root, ".git")):
        return {os.path.basename(os.path.normpath(root)): root}
    return {name: os.path.join(root, name) for name in sorted(os.listdir(root))
            if os.path.exists(os.path.join(root, name, ".git"))}


def pick_ref(repo: str, candidates) -> str:
    for ref in candidates:
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0:
            return ref
    return ""
