"""
Dépôts de code partagés par les étapes (Lancement, Cucumber) : copies locales du Standard, du client et du Cucumber
Standard (clone, fetch, sauvegarde des commits non poussés), version d'Odatio. Extraits tels quels de main.py
d'agent-scrum-master, avec leurs aides de tools/client_version.py, cucumber_delivery.py, cucumber_tools.py.
"""
import os
import re
import requests
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from agent_socle import versions as sv
from agent_socle.chemins import DATA_DIR
from agent_socle.cli import _read_text
from agent_socle.git_tools import _git
from urllib.parse import urlsplit


def _version_key(text: str) -> tuple:
    short = sv.normalize(text)[0]
    return tuple(int(p) for p in short.split(".")) if short else ()


def cucumber_std_ref(version: str, refs: list) -> dict:
    """
    Référence du Cucumber Standard pour la version du Standard `version`, parmi ses branches et tags `refs`
    (noms) : release/<v>, v<v>, <v> ; à défaut la version existante la plus proche INFÉRIEURE, avec avertissement ;
    aucune : {"ref": ""} et avertissement (jamais de repli sur master). {"ref", "version", "avertissement"}.
    """
    wanted = _version_key(version)
    if not wanted:
        return {"ref": "", "version": "", "avertissement": f"version du Standard « {version or '?'} » illisible : "
                                                            f"référence du Cucumber Standard à choisir"}
    short = sv.normalize(version)[0]
    names = list(dict.fromkeys(r for r in refs or [] if r))
    for candidate in (f"release/{short}", f"v{short}", short):
        if candidate in names:
            return {"ref": candidate, "version": short, "avertissement": ""}
    versioned = [(k, n) for n in names if (k := _version_key(n)) and re.fullmatch(r"(?:release/|v)?[\d.]+", n)]
    lower = [(k, n) for k, n in versioned if k[:2] < wanted[:2]]
    if not lower:
        return {"ref": "", "version": "", "avertissement": f"aucune référence du Cucumber Standard pour {short} ni "
                                                            f"pour une version inférieure : à choisir (pas de repli "
                                                            f"sur master)"}
    key, name = max(lower, key=lambda kn: (kn[0], name_rank(kn[1])))
    found = ".".join(map(str, key[:2]))
    return {"ref": name, "version": found,
            "avertissement": f"Cucumber Standard {short} absent (aucune branche ni tag release/{short}, v{short}, "
                             f"{short}) : version existante la plus proche inférieure retenue, {name}"}


def name_rank(name: str) -> int:
    return 2 if name.startswith("release/") else 1 if name.startswith("v") else 0


def cucumber_std_names(cucumber_std_dir: str) -> list:
    """Branches distantes et tags du clone du Cucumber Standard (noms sans origin/)."""
    if not cucumber_std_dir:
        return []
    out = _git(cucumber_std_dir, "for-each-ref", "--format=%(refname)", "refs/remotes/origin", "refs/tags").stdout
    names = []
    for ref in out.splitlines():
        if ref.startswith("refs/tags/"):
            names.append(ref[len("refs/tags/"):])
        elif not ref.endswith("/HEAD"):
            names.append(ref[len("refs/remotes/origin/"):])
    return names


READ_ONLY_PUSH_URL = "lecture-seule://envoi-desactive"


def disable_push(repo_dir: str) -> None:
    """Copie de lecture : adresse d'envoi désactivée (un push y échoue, la garde le refuse avant Git)."""
    if repo_dir and os.path.isdir(os.path.join(repo_dir, ".git")):
        _git(repo_dir, "config", "remote.origin.pushurl", READ_ONLY_PUSH_URL)


# Ligne de journal de main.py lue par l'onglet Cucumber : référence Git retenue du Cucumber Standard
STD_REF_LOG = "[CUCUMBER STD] Référence Git retenue :"


def bitbucket_base_url(repo_url: str = "") -> str:
    """BITBUCKET_URL du .env, à défaut l'hôte de l'URL de dépôt fournie."""
    configured = os.getenv("BITBUCKET_URL", "").strip().rstrip("/")
    if configured or not repo_url.startswith("http"):
        return configured
    parts = urlsplit(repo_url)
    return f"{parts.scheme}://{parts.netloc}"


ODATIO_VERSION = re.compile(r"^\d{2}\.\d+(\.\d+)*$")


def odatio_version_from_pom(text: str) -> tuple:
    """
    (version d'Odatio, d'où elle vient) lue dans un pom.xml : propriété odatio / kis (…version), puis version du
    parent Odatio / KIS, puis version du projet — retenue seulement si elle a la forme d'une version Odatio (26.16,
    25.4.2) : la version propre d'un dépôt (1.0.0) n'est pas celle de la plateforme. ('', raison) sinon.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return "", f"pom.xml illisible ({e})"
    tag = lambda node: node.tag.rsplit("}", 1)[-1]  # noqa: E731
    clean = lambda v: (v or "").strip().replace("-SNAPSHOT", "")  # noqa: E731
    candidates = []
    for props in (n for n in root if tag(n) == "properties"):
        for prop in props:
            if re.search(r"(odatio|kis).*version|version.*(odatio|kis)", tag(prop), re.I):
                candidates.append((clean(prop.text), f"propriété <{tag(prop)}>"))
    parent = next((n for n in root if tag(n) == "parent"), None)
    if parent is not None:
        fields = {tag(n): (n.text or "") for n in parent}
        if re.search(r"odatio|kis", fields.get("groupId", "") + fields.get("artifactId", ""), re.I):
            candidates.append((clean(fields.get("version")), f"parent {fields.get('artifactId', '')}"))
    own = next((n for n in root if tag(n) == "version"), None)
    if own is not None:
        candidates.append((clean(own.text), "version du projet"))
    for version, origin in candidates:
        if ODATIO_VERSION.match(version or ""):
            return version, origin
    seen = ", ".join(f"{v or '?'} ({o})" for v, o in candidates) or "aucune"
    return "", f"aucune version au format Odatio (ex. 26.16) dans le pom ; vu : {seen}"


def detect_odatio_version(std_repo_path: str) -> str:
    """
    Version d'Odatio du dépôt Standard (pom.xml racine, voir odatio_version_from_pom) ; ODATIO_VERSION du .env
    prime. « dev » si elle est introuvable : aucune comparaison de version n'est alors faite.
    """
    forced = os.getenv("ODATIO_VERSION", "").strip()
    if forced:
        print(f"[VERSION ODATIO] {forced} (ODATIO_VERSION du .env)")
        return forced
    # Sans copie locale (Standard lu dans Bitbucket) : aucun pom lu, surtout pas celui du dossier courant
    pom_path = os.path.join(std_repo_path, "pom.xml") if std_repo_path else ""
    if pom_path and os.path.exists(pom_path):
        version, origin = odatio_version_from_pom(_read_text(pom_path))
        if version:
            print(f"[VERSION ODATIO] {version} ({origin} du pom du Standard)")
            return version
        print(f"[VERSION ODATIO] ⚠️ {origin} — renseignez ODATIO_VERSION (onglet Configuration) ; comparaisons de "
              f"version désactivées.")
    return "dev"


def _force_rmtree(path: str) -> None:
    """Supprime un dossier, y compris les fichiers en lecture seule d'un .git sous Windows."""
    def make_writable(func, target, _exc):
        os.chmod(target, 0o700)
        func(target)
    shutil.rmtree(path, **({"onexc": make_writable} if sys.version_info >= (3, 12) else {"onerror": make_writable}))


def _git_out(repo_dir: str, *args: str) -> str:
    # Sortie de git en UTF-8 (messages de commit accentués), pas dans l'encodage de la console Windows
    return subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def _same_git_url(a: str, b: str) -> bool:
    normalize = lambda url: re.sub(r"\.git$", "", url.strip().rstrip("/")).lower()
    return normalize(a) == normalize(b)


def cucumber_std_clone_dir(workspace_dir: str, clone_url: str) -> str:
    """Un clone par dépôt : .tmp/cucumber_std/<slug-projet>_<slug-dépôt>."""
    path = urlsplit(clone_url).path if "://" in clone_url else clone_url.split(":", 1)[-1]
    parts = [p for p in path.split("/") if p and p != "scm"]
    slug = lambda text: re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"
    repo = re.sub(r"\.git$", "", parts[-1]) if parts else "cucumber"
    project = parts[-2] if len(parts) >= 2 else "std"
    return os.path.join(workspace_dir, ".tmp", "cucumber_std", f"{slug(project)}_{slug(repo)}")


def checkout_cucumber_std_ref(repo_dir: str, odatio_version: str) -> str:
    """
    Détache le clone sur la référence de la version du Standard : release/<v>, v<v>, <v> (branches distantes, puis
    tags) ; absente : version existante la plus proche INFÉRIEURE, avec un avertissement explicite — jamais de repli
    silencieux sur master. Seule une version illisible (« dev ») prend origin/dev, main, master, HEAD, signalé.
    Jamais une branche locale, qui peut être en retard sur le distant. Renvoie la référence retenue ('' si aucune).
    """
    clean_ver = odatio_version.replace("-SNAPSHOT", "").strip()
    if sv.normalize(clean_ver)[0]:
        picked = cucumber_std_ref(clean_ver, cucumber_std_names(repo_dir))
        if picked["avertissement"]:
            print(f"[CUCUMBER STD] ⚠️ {picked['avertissement']}")
        if not picked["ref"]:
            return ""
        name = picked["ref"]
        candidates = [f"origin/{name}", f"refs/tags/{name}"]
    else:
        print(f"[CUCUMBER STD] ⚠️ Version du Standard illisible ({odatio_version or 'vide'}) : branche de "
              f"développement du Cucumber Standard retenue (dev, main, master).")
        candidates = ["origin/dev", "origin/main", "origin/master", "origin/HEAD"]
    for ref in candidates:
        if not _git_out(repo_dir, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
            continue
        res = subprocess.run(["git", "-C", repo_dir, "checkout", "-q", "--force", "--detach", ref],
                             capture_output=True, text=True)
        if res.returncode == 0:
            return ref.removeprefix("refs/tags/")
        print(f"⚠️ Checkout de '{ref}' impossible : {res.stderr.strip()[:300]}")
    return ""


def ensure_cucumber_std_repo(repo_url: str, odatio_version: str) -> tuple:
    """
    Prépare le dépôt Cucumber Standard et renvoie (dossier, "référence @ commit court") ; ("", "") si indisponible.
    - chemin local d'un dépôt git : utilisé tel quel (fetch seulement, aucun checkout) ;
    - URL (navigation Bitbucket, clonable ou projet Bitbucket) : un clone par dépôt, recloné si son origin diffère,
      puis fetch et checkout détaché de la référence distante correspondant à la version Odatio.
    """
    repo_url = (repo_url or "").strip()
    if not repo_url:
        return "", ""

    bitbucket_token = os.getenv("BITBUCKET_HTTP_TOKEN", "").strip()
    git_env = os.environ.copy()
    git_cmd_extra = ["-c", f"http.extraHeader=Authorization: Bearer {bitbucket_token}"] if bitbucket_token else []

    def fetch(repo_dir: str) -> None:
        res = subprocess.run(["git"] + git_cmd_extra + ["-C", repo_dir, "fetch", "--all", "--tags", "--force", "--prune"],
                             capture_output=True, text=True, env=git_env)
        if res.returncode != 0:
            print(f"⚠️ git fetch du Cucumber Standard en échec : {res.stderr.strip()[:300]}")

    def report(repo_dir: str, ref: str) -> tuple:
        label = f"{ref} @ {_git_out(repo_dir, 'rev-parse', '--short', 'HEAD')}"
        print(f"[CUCUMBER STD] Dossier : {repo_dir}")
        print(f"{STD_REF_LOG} {label}")
        print(f"==================================================\n")
        return repo_dir, label

    print(f"\n==================================================")
    print(f"[CUCUMBER STD] Préparation des tests Cucumber Standard (Version cible Odatio : {odatio_version})...")

    # Chemin local : le dépôt de l'utilisateur n'est ni cloné ni basculé de branche
    if not repo_url.startswith(("http://", "https://", "git@", "file://")):
        local_dir = os.path.abspath(repo_url)
        if not os.path.exists(os.path.join(local_dir, ".git")):
            print(f"❌ Dépôt Cucumber Standard '{repo_url}' : ni URL ni dossier git local.")
            return "", ""
        print(f"📂 Dépôt Cucumber Standard local utilisé tel quel : {local_dir}")
        fetch(local_dir)
        branch = _git_out(local_dir, "rev-parse", "--abbrev-ref", "HEAD")
        return report(local_dir, branch if branch and branch != "HEAD" else "HEAD détaché")

    clean_url = repo_url.split("/browse")[0].rstrip("/")
    # URL de navigation Bitbucket (.../projects/COMPONENT-QA/repos/cucumber) -> URL clonable (.../scm/component-qa/cucumber.git)
    web_repo = re.match(r"^(https?://[^/]+)/projects/([^/]+)/repos/([^/]+)$", clean_url)
    if web_repo:
        clean_url = f"{web_repo.group(1)}/scm/{web_repo.group(2).lower()}/{web_repo.group(3)}.git"
    bitbucket_url = bitbucket_base_url(clean_url)

    if "/projects/" in clean_url and "/repos/" not in clean_url and not clean_url.endswith(".git"):
        project_key = clean_url.split("/")[-1].upper()
        print(f"[CUCUMBER STD] Recherche du dépôt Cucumber dans le projet '{project_key}'...")
        api_url = f"{bitbucket_url}/rest/api/1.0/projects/{project_key}/repos?limit=100"
        headers = {"Authorization": f"Bearer {bitbucket_token}"} if bitbucket_token else {}
        try:
            res = requests.get(api_url, headers=headers, timeout=10)
            repos = res.json().get("values", []) if res.status_code == 200 else []
        except Exception as e:
            print(f"[CUCUMBER STD] Erreur API Bitbucket ({e})")
            return "", ""
        cuc_repo = (next((r["slug"] for r in repos if "cucumber" in r["slug"].lower()), None)
                    or next((r["slug"] for r in repos if "qa" in r["slug"].lower()), None))
        if not cuc_repo:
            print(f"[CUCUMBER STD] Aucun dépôt Cucumber trouvé dans le projet {project_key}.")
            return "", ""
        clean_url = f"{bitbucket_url}/scm/{project_key.lower()}/{cuc_repo}.git"
        print(f"[CUCUMBER STD] Dépôt trouvé via API Bitbucket : {clean_url}")

    if not clean_url.endswith(".git") and "/scm/" in clean_url:
        clean_url += ".git"
    print(f"URL Git : {clean_url}")

    workspace_dir = DATA_DIR  # .tmp des copies locales : AGENT_DATA_DIR
    root_dir = os.path.join(workspace_dir, ".tmp", "cucumber_std")
    target_dir = cucumber_std_clone_dir(workspace_dir, clean_url)
    # Ancienne disposition : un clone unique directement dans .tmp/cucumber_std
    if os.path.exists(os.path.join(root_dir, ".git")):
        print(f"🧹 Suppression de l'ancien clone unique {root_dir}...")
        _force_rmtree(root_dir)

    if os.path.exists(os.path.join(target_dir, ".git")):
        origin = _git_out(target_dir, "remote", "get-url", "origin")
        if not _same_git_url(origin, clean_url):
            print(f"🧹 Clone {target_dir} issu d'un autre dépôt ({origin or 'origin absent'}) : reclonage.")
            _force_rmtree(target_dir)

    if os.path.exists(os.path.join(target_dir, ".git")):
        print(f"🔄 Mise à jour du dépôt Cucumber Standard dans {target_dir}...")
        fetch(target_dir)
    else:
        if os.path.exists(target_dir):
            _force_rmtree(target_dir)
        print(f"📥 Clonage du dépôt Cucumber Standard depuis {clean_url} dans {target_dir}...")
        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        res = subprocess.run(["git"] + git_cmd_extra + ["clone", "--no-checkout", clean_url, target_dir],
                             capture_output=True, text=True, env=git_env)
        if res.returncode != 0:
            print(f"❌ Échec du clonage Cucumber Standard : {res.stderr.strip()}")
            return "", ""

    # Cucumber Standard : copie de lecture, aucune adresse d'envoi
    disable_push(target_dir)
    ref = checkout_cucumber_std_ref(target_dir, odatio_version)
    if not ref:
        print("❌ Aucune référence distante exploitable (version Odatio, dev, main, master) dans le Cucumber Standard.")
        return "", ""
    return report(target_dir, ref)


BACKUP_DIR = os.path.join(DATA_DIR, ".tmp", "sauvegardes")


def update_clone(repo_dir: str, name: str, git_cmd_extra: list = (), git_env: dict = None) -> tuple:
    """
    Mise à jour d'une copie de code par « git fetch » (jamais de pull : les lectures se font sur les références
    distantes, la branche locale et l'arbre de travail ne sont pas touchés). Les commits locaux non poussés sont
    d'abord sauvegardés dans un bundle (.tmp/sauvegardes/<dépôt>-<date>.bundle). Renvoie (succès, message).
    """
    unpushed = subprocess.run(["git", "-C", repo_dir, "log", "--branches", "--not", "--remotes", "--oneline"],
                              capture_output=True, text=True).stdout.strip().splitlines()
    saved = ""
    if unpushed:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        saved = os.path.join(BACKUP_DIR, f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.bundle")
        bundle = subprocess.run(["git", "-C", repo_dir, "bundle", "create", saved, "--branches", "--not",
                                 "--remotes"], capture_output=True, text=True)
        if bundle.returncode != 0:
            return False, (f"{name} : sauvegarde des {len(unpushed)} commit(s) local(aux) non poussé(s) impossible "
                           f"({bundle.stderr.strip()[:200]}) : dépôt non mis à jour")
    res = subprocess.run(["git", *git_cmd_extra, "-C", repo_dir, "fetch", "--prune", "origin"],
                         capture_output=True, text=True, env=git_env)
    backup = f" ; {len(unpushed)} commit(s) local(aux) non poussé(s) sauvegardé(s) dans {saved}" if saved else ""
    if res.returncode != 0:
        return False, f"Erreur fetch sur {name} : {res.stderr.strip()[:300]}{backup}"
    synced = sync_working_copy(repo_dir)
    return True, f"{name} mis à jour (fetch){backup}" + (f" ; {synced}" if synced else "") + "."


def sync_working_copy(repo_dir: str, default_branch: str = "integration") -> str:
    """
    Fichiers de la copie de l'agent remis à jour quand c'est sans risque (Claude lit le code dans ces fichiers) :
    - modifications non commitées ou fusion en cours : rien n'est touché ;
    - branche suivie en retard : avance rapide (merge --ff-only), jamais de fusion ni de réécriture ;
    - branche de travail non suivie (ex. SPEC-1996_dev_…) : la copie revient sur la branche d'intégration suivie,
      la branche et ses commits restent intacts (et déjà sauvegardés dans un bundle s'ils ne sont pas poussés).
    Renvoie ce qui a été fait ('' si rien).
    """
    def git(*args):
        return subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip() or \
            git("rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        return ""
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode != 0:
        if branch == "HEAD" or git("rev-parse", "-q", "--verify", f"origin/{default_branch}").returncode != 0:
            return ""
        exists = git("rev-parse", "-q", "--verify", f"refs/heads/{default_branch}").returncode == 0
        done = git("checkout", "-q", default_branch) if exists else \
            git("checkout", "-q", "-b", default_branch, "--track", f"origin/{default_branch}")
        if done.returncode != 0:
            return ""
        if exists:
            git("branch", "-q", f"--set-upstream-to=origin/{default_branch}")
        moved = f"copie remise sur {default_branch} (la branche {branch} est conservée)"
    else:
        moved = ""
    behind = git("rev-list", "--count", "HEAD..@{u}").stdout.strip()
    if behind.isdigit() and int(behind) and git("merge", "-q", "--ff-only", "@{u}").returncode == 0:
        return (moved + " ; " if moved else "") + f"{behind} commit(s) appliqué(s) en avance rapide"
    return moved


def fetch_age_minutes(repo_dir: str):
    """Minutes depuis le dernier fetch du clone (date de .git/FETCH_HEAD), None s'il n'a jamais été récupéré."""
    head = os.path.join(repo_dir, ".git", "FETCH_HEAD")
    return (time.time() - os.path.getmtime(head)) / 60 if os.path.exists(head) else None


def std_fetch_max_age() -> float:
    """
    Âge maximal (minutes) d'un fetch du Standard réutilisé sans nouveau fetch : STD_FETCH_MAX_AGE_MINUTES (1440, un
    jour : le code du Standard lu par l'analyse n'a pas besoin d'être à la minute ; 0 = toujours récupérer).
    """
    try:
        return max(0.0, float(os.getenv("STD_FETCH_MAX_AGE_MINUTES", "1440")))
    except ValueError:
        return 1440.0


def fetch_workers() -> int:
    """Récupérations Git menées en parallèle (GIT_FETCH_WORKERS, 8)."""
    try:
        return max(1, int(os.getenv("GIT_FETCH_WORKERS", "8")))
    except ValueError:
        return 8


def ensure_local_repo(repo_input: str, repo_label: str, only: list = None) -> str:
    """
    Si repo_input est une URL de projet Bitbucket, interroge l'API REST 
    pour récupérer et cloner / mettre à jour TOUS les dépôts du projet.
    """
    if not repo_input or repo_input == "STD_ONLY":
        return ""

    if not (repo_input.startswith("http://") or repo_input.startswith("https://") or repo_input.startswith("git@")):
        print(f"[LOCAL REPO] Utilisation du chemin local fourni pour '{repo_label}' : {repo_input}")
        return repo_input

    workspace_dir = DATA_DIR  # .tmp des copies locales : AGENT_DATA_DIR
    tmp_dir = os.path.join(workspace_dir, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    bitbucket_token = os.getenv("BITBUCKET_HTTP_TOKEN", "").strip()
    bitbucket_url = bitbucket_base_url(repo_input)

    git_env = os.environ.copy()
    git_cmd_extra = ["-c", f"http.extraHeader=Authorization: Bearer {bitbucket_token}"] if bitbucket_token else []

    if "/projects/" in repo_input and "/repos/" not in repo_input and not repo_input.endswith(".git"):
        project_key = repo_input.rstrip("/").split("/")[-1].upper()
        target_dir = os.path.join(tmp_dir, f"{repo_label}_{project_key}")
        os.makedirs(target_dir, exist_ok=True)

        print(f"\n==================================================")
        print(f"[API BITBUCKET] Interrogation du projet '{project_key}' sur {bitbucket_url}...")

        api_url = f"{bitbucket_url}/rest/api/1.0/projects/{project_key}/repos"
        headers = {"Authorization": f"Bearer {bitbucket_token}"} if bitbucket_token else {}

        repos_to_clone = []
        try:
            # Toutes les pages : un projet peut compter plus de 100 dépôts (le Standard en a plus de 170)
            start = 0
            while True:
                res = requests.get(api_url, headers=headers, params={"start": start, "limit": 100}, timeout=10)
                if res.status_code != 200:
                    print(f"[API BITBUCKET] Code retour {res.status_code}"
                          + (", passage sur la liste de secours." if not repos_to_clone else
                             f" sur la page {start} : liste partielle."))
                    break
                data = res.json()
                repos_to_clone += [repo["slug"] for repo in data.get("values", [])]
                if data.get("isLastPage", True):
                    break
                start = data.get("nextPageStart", start + 100)
            if repos_to_clone:
                print(f"[API BITBUCKET] {len(repos_to_clone)} dépôt(s) trouvé(s) pour {project_key} : {', '.join(repos_to_clone)}")
        except Exception as e:
            print(f"[API BITBUCKET] Erreur API ({e}), passage sur la liste de secours.")

        if not repos_to_clone:
            repos_to_clone = [
                f"odatio-{project_key.lower()}",
                f"odatio-ui-{project_key.lower()}",
                "studio",
                "wms-goodsin-backend",
                "wms-preparation-backend",
                "traduction"
            ]
            print(f"[API BITBUCKET] Liste de secours chargée : {', '.join(repos_to_clone)}")

        print(f"[GIT REPO] Dossier cible local : {target_dir}")
        print(f"==================================================\n")

        skipped = []
        if only is not None:
            print(f"[GIT REPO] {len(set(only) & set(repos_to_clone))} dépôt(s) sur {len(repos_to_clone)} utiles au client "
                  f"(modules déployés et dépôts transverses) : les autres ne sont ni clonés ni récupérés.")
            repos_to_clone = [r for r in repos_to_clone if r in set(only)]
        def sync_one(idx: int, repo_name: str) -> str:
            """Fetch ou clonage d'un dépôt ; renvoie les lignes de journal (affichées dans l'ordre)."""
            repo_dir = os.path.join(target_dir, repo_name)
            clone_url = f"{bitbucket_url}/scm/{project_key}/{repo_name}.git"
            if os.path.exists(os.path.join(repo_dir, ".git")):
                ok, message = update_clone(repo_dir, repo_name, git_cmd_extra, git_env)
                lines = (f"[{idx}/{len(repos_to_clone)}] 🔄 Mettre à jour {repo_name} dans {repo_dir}...\n"
                         f"     {'✅' if ok else '⚠️'} {message}")
            else:
                cmd = ["git"] + git_cmd_extra + ["clone", clone_url, repo_dir]
                res_clone = subprocess.run(cmd, capture_output=True, text=True, env=git_env)
                lines = (f"[{idx}/{len(repos_to_clone)}] 📥 Clonage de {repo_name} depuis {clone_url}...\n     "
                         + (f"✅ {repo_name} cloné avec succès." if res_clone.returncode == 0 else
                            f"❌ Échec clonage {repo_name} : {res_clone.stderr.strip()}"))
            if repo_label == "std" or "cucumber" not in repo_name.lower():
                # Copie de lecture (code client, Standard, Studio) : aucune adresse d'envoi
                disable_push(repo_dir)
            return lines

        todo = []
        for idx, repo_name in enumerate(repos_to_clone, 1):
            repo_dir = os.path.join(target_dir, repo_name)
            age = fetch_age_minutes(repo_dir) if os.path.exists(os.path.join(repo_dir, ".git")) else None
            if repo_label == "std" and age is not None and age < std_fetch_max_age():
                # Standard récupéré récemment : pas de nouveau fetch (STD_FETCH_MAX_AGE_MINUTES, 0 = toujours)
                skipped.append(repo_name)
                continue
            todo.append((idx, repo_name))
        # Récupérations en parallèle (réseau) ; journal dans l'ordre des dépôts
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(fetch_workers(), max(1, len(todo)))) as pool:
            for lines in pool.map(lambda item: sync_one(*item), todo):
                print(lines)

        if skipped:
            print(f"[GIT REPO] {len(skipped)} dépôt(s) du Standard récupéré(s) il y a moins de "
                  f"{std_fetch_max_age() / 60:g} h : fetch sauté (STD_FETCH_MAX_AGE_MINUTES, 0 pour toujours "
                  f"récupérer).")
        print(f"\n[GIT COMPLETE] Traitement terminé pour le projet {project_key}.\n")
        return target_dir

    else:
        clean_name = repo_input.rstrip("/").split("/")[-1].replace(".git", "")
        target_dir = os.path.join(tmp_dir, f"{repo_label}_{clean_name}")

        print(f"\n[GIT SINGLE REPO] Traitement du dépôt unique : {repo_input}")
        if os.path.exists(target_dir) and os.path.exists(os.path.join(target_dir, ".git")):
            print(f"🔄 Mettre à jour le dépôt local {repo_label} : {target_dir}")
            ok, message = update_clone(target_dir, clean_name, git_cmd_extra, git_env)
            print(f"{'✅' if ok else '⚠️'} {message}")
        else:
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
            print(f"📥 Clonage automatique du dépôt {repo_label} depuis {repo_input}...")
            cmd = ["git"] + git_cmd_extra + ["clone", repo_input, target_dir]
            res_clone = subprocess.run(cmd, capture_output=True, text=True, env=git_env)
            if res_clone.returncode == 0:
                print(f"✅ {clean_name} cloné avec succès.")
            else:
                print(f"❌ Erreur lors du clonage de {repo_input} :\n{res_clone.stderr.strip()}")
                return repo_input
        if repo_label == "std" or "cucumber" not in clean_name.lower():
            disable_push(target_dir)
        return target_dir


# Copie locale du Standard préparée au démarrage (lectures des contrôles hors du flux principal)
STD_LOCAL_ROOT = [""]


# Source du Standard pour les contrôles déterministes : RemoteStandard (Bitbucket) ou dossier de clones
STD_READER = [""]
