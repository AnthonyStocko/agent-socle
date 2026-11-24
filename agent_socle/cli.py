"""
Fonctions communes des CLI d'agents, extraites telles quelles de main.py d'agent-scrum-master : appel de Claude Code
(run_claude), modèles de prompts, mesure des tokens, doc ODATiO, connaissances partagées ; et `deleguer`
(compatibilité : `main.py --step X` d'agent-scrum-master relance la CLI de l'agent qui porte l'étape).

Prompts : PROMPTS_DIR, puis ceux de l'agent (DEFAULT_PROMPTS_DIR, renseigné par son main.py), puis ceux du socle.
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from string import Template

from agent_socle import groundcover_tools, knowledge_tools, mcp_servers, odatio_docs, token_measure
from agent_socle.chemins import DATA_DIR

# Modèles communs à tous les agents (token_saving_rules, odatio_docs, db_access)
SOCLE_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
# Modèles de l'agent appelant (son dossier prompts/), renseigné par son main.py
DEFAULT_PROMPTS_DIR = ""


def _read_text(path: str) -> str:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return ""


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    try:
        return max(int(value), 0) if value else default
    except ValueError:
        print(f"[CONFIG] ⚠️ {name}='{value}' n'est pas un nombre : valeur par défaut {default} utilisée.")
        return default


TOKEN_USAGE_CSV = os.path.join(DATA_DIR, ".tmp", "token_usage.csv")


TOKEN_USAGE_FIELDS = ["date", "ticket", "etape", "modele", "effort", "tokens_entree", "cache_ecrit", "cache_lu",
                      "tokens_sortie", "tours", "duree_s", "cout_usd", "taille_prompt", "code_retour",
                      # Mesure du contexte (tools/token_measure.py) : session, reprise (--resume), cumul de la session,
                      # contexte relu par tour, résultats d'outils de l'appel (nombre, caractères, détail par outil)
                      "session", "reprise", "cout_session", "contexte_tour", "outils_appels", "outils_car",
                      "outils_detail"]


CLAUDE_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def claude_effort(*names: str) -> str:
    """Première variable .env renseignée parmi `names` ; valeur hors CLAUDE_EFFORT_LEVELS : avertissement et vide."""
    value = next((v for v in (os.getenv(n, "").strip().lower() for n in names) if v), "")
    if value and value not in CLAUDE_EFFORT_LEVELS:
        print(f"[CONFIG] ⚠️ Effort Claude '{value}' ({' / '.join(names)}) invalide, attendu : "
              f"{', '.join(CLAUDE_EFFORT_LEVELS)}. Option --effort non envoyée.")
        return ""
    return value


def render_prompt(name: str, **values) -> str:
    """
    Modèle '<name>.md' complété par ses variables ${nom} (string.Template, '$$' pour un '$' littéral).
    Cherché d'abord dans PROMPTS_DIR (prompts personnalisés), sinon dans le dossier prompts/ du projet.
    """
    custom_dir = os.getenv("PROMPTS_DIR", "").strip()
    path = ""
    for directory in ([custom_dir] if custom_dir else []) + [d for d in (DEFAULT_PROMPTS_DIR, SOCLE_PROMPTS_DIR) if d]:
        candidate = os.path.join(directory, f"{name}.md")
        if os.path.exists(candidate):
            path = candidate
            break
    if not path:
        sys.exit(f"[PROMPTS] ❌ Modèle de prompt '{name}.md' introuvable (PROMPTS_DIR='{custom_dir}', {DEFAULT_PROMPTS_DIR}).")
    try:
        return Template(_read_text(path)).substitute({**OPTIONAL_PROMPT_VALUES, **values})
    except (KeyError, ValueError) as e:
        sys.exit(f"[PROMPTS] ❌ Modèle '{path}' invalide : variable inconnue ou '$' isolé ({e}). "
                 f"Variables disponibles : {', '.join(sorted(values)) or 'aucune'}.")


# Blocs facultatifs des modèles : vides quand l'appel ne les fournit pas (ex. doc ODATiO non transmise à un appel)
OPTIONAL_PROMPT_VALUES = {"odatio_docs_block": ""}


# Documentation développeur ODATiO (tools/odatio_docs.py) : lecture seule, limitée au site de ODATIO_DOCS_URL
ODATIO_DOCS_CLI = os.path.join(os.path.dirname(os.path.abspath(odatio_docs.__file__)), "odatio_docs.py")


ODATIO_DOCS_USAGE = {
    "analyse": "l'analyse et le cadrage du ticket et son chiffrage",
    "patch": "le développement du patch et la correction du code",
    "revue": "la relecture des pull requests",
    "cucumber": "la génération et la correction des tests Cucumber",
}


def odatio_docs_block(python_exe: str, usage: str) -> str:
    """Consigne de consultation de la doc ODATiO (prompts/odatio_docs.md) ; '' si ODATIO_DOCS_URL est vide."""
    if not odatio_docs.enabled():
        return ""
    return "\n" + render_prompt("odatio_docs", cli=f'"{python_exe}" "{ODATIO_DOCS_CLI}"', docs_url=odatio_docs.base_url(),
                                usage=ODATIO_DOCS_USAGE.get(usage, usage),
                                max_consultations=str(_env_int("ODATIO_DOCS_MAX_CONSULTATIONS", 6))).strip() + "\n"


def odatio_docs_tools(python_exe: str) -> list:
    """Motifs --allowedTools de l'outil de la doc ODATiO (seule commande autorisée) ; [] si la doc est désactivée."""
    if not odatio_docs.enabled():
        return []
    return [f"Bash({python_exe} {ODATIO_DOCS_CLI}:*)", f'Bash("{python_exe}" "{ODATIO_DOCS_CLI}":*)']


def parse_claude_output(raw: str) -> tuple:
    """
    Sortie de `claude --print --output-format json` -> (texte de la réponse, usage).
    Repli si la sortie n'est pas du JSON : (sortie brute, None).
    """
    raw = raw or ""
    candidates = [raw.strip()] + [l.strip() for l in reversed(raw.splitlines()) if l.strip().startswith(("{", "["))]
    data = None
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(obj, list):
            obj = next((m for m in reversed(obj) if isinstance(m, dict) and m.get("type") == "result"), None)
        if isinstance(obj, dict) and (obj.get("type") == "result" or "result" in obj):
            data = obj
            break
    if data is None:
        return raw, None

    text = data.get("result")
    if not isinstance(text, str):
        text = f"[Claude Code] Fin sans réponse texte ({data.get('subtype', 'inconnu')})."
    u = data.get("usage") or {}
    keys = {"tokens_entree": ("input_tokens", "inputTokens"),
            "cache_ecrit": ("cache_creation_input_tokens", "cacheCreationInputTokens"),
            "cache_lu": ("cache_read_input_tokens", "cacheReadInputTokens"),
            "tokens_sortie": ("output_tokens", "outputTokens")}
    usage = {key: u.get(name, 0) or 0 for key, (name, _) in keys.items()}
    if not any(usage.values()):
        # Arrêt sur budget (--max-budget-usd) : usage global à zéro, le détail reste dans modelUsage
        models = (data.get("modelUsage") or {}).values()
        usage = {key: sum((m.get(name) or 0) for m in models) for key, (_, name) in keys.items()}
    usage.update({
        "tours": data.get("num_turns", ""),
        "duree_s": round((data.get("duration_ms") or 0) / 1000, 1),
        "cout_usd": data.get("total_cost_usd", ""),
        "modeles": ",".join((data.get("modelUsage") or {}).keys()),
        "fin": data.get("subtype", ""),
        "session_id": data.get("session_id", ""),
    })
    return text, usage


def lean_session() -> bool:
    """CLAUDE_LEAN_SESSION (défaut 1) : sessions Cucumber allégées (outils demandés seuls, sans MCP ni commandes)."""
    return os.getenv("CLAUDE_LEAN_SESSION", "1").strip() != "0"


def budget_hit(usage: dict) -> bool:
    """L'appel s'est arrêté sur --max-budget-usd."""
    return "budget" in str((usage or {}).get("fin", ""))


def claude_command(model: str, add_dirs: list, allowed_tools: list, extra_args: tuple = (), effort: str = "",
                   lean: bool = False, budget_usd: str = "", mcp: dict = None) -> list:
    """
    Ligne de commande `claude --print`. `lean` : seules les définitions des outils autorisés sont envoyées
    (--tools, noms sans motif : Bash(python:*) -> Bash), sans serveur MCP, commandes ni skills, et les sections
    propres au poste sorties du prompt système. `budget_usd` : --max-budget-usd. `mcp` (mcp_servers.claude_args,
    étapes de diagnostic seulement) : --mcp-config du seul serveur Groundcover, --strict-mcp-config gardé, ses outils
    de lecture ajoutés à --allowedTools.
    """
    cmd = [shutil.which("claude") or "claude", "--print", "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])
    if effort in CLAUDE_EFFORT_LEVELS:
        cmd.extend(["--effort", effort])
    elif effort:
        print(f"[CONFIG] ⚠️ Effort Claude '{effort}' invalide, attendu : {', '.join(CLAUDE_EFFORT_LEVELS)}. "
              f"Option --effort non envoyée.")
    if lean:
        cmd.extend(["--tools", *dict.fromkeys(t.split("(", 1)[0] for t in allowed_tools)])
        cmd.extend(["--strict-mcp-config", "--disable-slash-commands", "--exclude-dynamic-system-prompt-sections"])
    if mcp:
        # Liste fermée : seuls les serveurs du fichier --mcp-config sont chargés (Groundcover, jamais Jira)
        if "--strict-mcp-config" not in cmd:
            cmd.append("--strict-mcp-config")
        cmd.extend(mcp["args"])
    if budget_usd:
        cmd.extend(["--max-budget-usd", budget_usd])
    for directory in add_dirs:
        cmd.extend(["--add-dir", directory])
    cmd.extend(extra_args)
    cmd.extend(["--allowedTools", *allowed_tools, *((mcp or {}).get("tools") or [])])
    return cmd


def claude_env() -> dict:
    """
    Environnement des appels `claude` : CLAUDE_CONFIG_DIR (onglet Configuration) choisit le compte Claude,
    c.-à-d. le dossier de configuration et d'identifiants de la CLI. Vide = compte par défaut (~/.claude).
    """
    env = os.environ.copy()
    config_dir = env.pop("CLAUDE_CONFIG_DIR", "").strip()
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = os.path.expanduser(config_dir)
    return env


# Limite d'usage de Claude Code : « You've hit your session limit », « You've hit your 5-hour limit · resets 7:30pm
# (Europe/Paris) », limite hebdomadaire… (le libellé change selon la version de Claude Code et le type de limite)
_USAGE_LIMIT = re.compile(r"hit your [\w -]*limit", re.I)


_USAGE_RESET = re.compile(r"hit your [\w -]*limit\s*[·•-]?\s*(resets [^\n]+)", re.I)


def usage_limit_hit(text: str) -> bool:
    """Réponse de Claude Code refusée par une limite d'usage (aucun travail fait : ni tentative ni échec à compter)."""
    return bool(_USAGE_LIMIT.search(text or ""))


def usage_limit_reset(text: str) -> str:
    """Heure de reprise annoncée par le message de limite (« resets 7:30pm (Europe/Paris) »), '' si absente."""
    match = _USAGE_RESET.search(text or "")
    return match.group(1).strip() if match else ""


def run_claude(prompt: str, model: str, add_dirs: list, allowed_tools: list, extra_args: tuple = (),
               cwd: str = None, effort: str = "", lean: bool = False, budget_usd: str = "",
               env: dict = None, mcp_step: str = "") -> tuple:
    """
    Exécute `claude --print` sur le prompt (envoyé sur stdin) et affiche sa réponse.
    Renvoie (code retour, texte de la réponse, usage des tokens, quota atteint) ; usage["fin"] : subtype du résultat
    (error_max_budget_usd si le budget est atteint, cf. budget_hit). `env` : environnement du sous-processus
    (par défaut claude_env()). `mcp_step` : étape de diagnostic qui reçoit Groundcover s'il est activé
    (mcp_servers.DIAGNOSTIC_STEPS) ; la réponse est alors masquée (lignes de log) avant tout affichage ou stockage.
    """
    mcp = mcp_servers.claude_args(mcp_step) if mcp_step else None
    cmd = claude_command(model, add_dirs, allowed_tools, extra_args, effort, lean, budget_usd, mcp)
    if mcp:
        env = mcp_servers.agent_env(env if env is not None else claude_env())

    # stderr séparé : la sortie standard doit rester du JSON exploitable
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=(os.name == "nt"),
        cwd=cwd,
        env=env if env is not None else claude_env(),
    )

    raw_stdout, raw_stderr = process.communicate(input=prompt)
    # Texte de la réponse (champ `result`), ou sortie brute en repli si ce n'est pas du JSON
    stdout_output, token_usage = parse_claude_output(raw_stdout)
    if raw_stderr and raw_stderr.strip():
        stdout_output = f"{stdout_output.rstrip()}\n{raw_stderr.strip()}" if stdout_output.strip() else raw_stderr.strip()
    session_limit_hit = usage_limit_hit(stdout_output)
    if mcp:
        stdout_output = groundcover_tools.mask(stdout_output)
        failure = mcp_servers.access_failure(stdout_output)
        if failure:
            mcp_servers.record_access_failure(failure)
            print(f"[LOGS] ⚠️ {mcp_servers.failure_message(failure)}")

    if stdout_output:
        print(stdout_output)
        if session_limit_hit:
            reset = usage_limit_reset(stdout_output)
            print("\n⚠️ QUOTA ATTEINT : La session Claude Code a atteint sa limite d'utilisation"
                  + (f" ({reset}) : « Reprendre » après cette heure." if reset else "."))
    if budget_hit(token_usage):
        print(f"\n⚠️ BUDGET ATTEINT : arrêt de l'appel à --max-budget-usd {budget_usd}.")
    return process.returncode, stdout_output, token_usage, session_limit_hit


def report_token_usage(issue: str, step: str, model: str, usage: dict, prompt_chars: int, returncode: int,
                       effort: str = "") -> None:
    """Affiche la ligne [TOKENS] et l'ajoute à .tmp/token_usage.csv (ne fait jamais échouer l'étape)."""
    if not usage:
        print(f"\n[TOKENS] Usage indisponible (sortie de Claude Code non JSON) — prompt : {prompt_chars} caractères.")
        return
    model_label = usage.get("modeles") or model or "défaut"
    cost = usage.get("cout_usd")
    # Reprise (--resume) : le cumul de la session dépasse le coût propre de l'appel (cucumber_cost.call_cost)
    resumed = token_measure.is_resumed(usage)
    # Session reprise sans cumul connu : Claude Code renvoie le coût cumulé de toute la session
    cost_label = (f"{cost:.4f} $" + (" (cumul de la session)" if usage.get("cout_cumul_inconnu") else "")
                  if isinstance(cost, (int, float)) else "?")
    context = token_measure.context_per_turn(usage)
    try:
        tools_used = token_measure.tool_stats(usage.get("session_id", ""))
    except Exception:  # mesure au mieux : jamais d'échec de l'étape
        tools_used = {}
    print(f"\n[TOKENS] entrée={usage['tokens_entree']} | cache écrit={usage['cache_ecrit']} | "
          f"cache lu={usage['cache_lu']} | sortie={usage['tokens_sortie']} | tours={usage['tours']} | "
          f"coût={cost_label} | durée={usage['duree_s']} s | modèle={model_label} | effort={effort or 'défaut'} | "
          f"prompt={prompt_chars} car. | contexte/tour={round(context / 1000)}k | reprise={'oui' if resumed else 'non'}")
    if tools_used.get("appels"):
        print(f"[CONTEXTE] Résultats d'outils de l'appel : {tools_used['appels']} résultat(s), "
              f"{round(tools_used['car'] / 1000)}k car. — {token_measure.detail_text(tools_used)} ; le plus gros : "
              f"{tools_used['plus_gros'][0]} {round(tools_used['plus_gros'][1] / 1000)}k car.")
    row = {
        "date": datetime.now().isoformat(timespec="seconds"), "ticket": issue, "etape": step,
        "modele": model_label, "effort": effort, "taille_prompt": prompt_chars, "code_retour": returncode,
        **{k: usage.get(k, "") for k in ("tokens_entree", "cache_ecrit", "cache_lu", "tokens_sortie",
                                          "tours", "duree_s", "cout_usd")},
        "session": usage.get("session_id", ""), "reprise": "oui" if resumed else "non",
        "cout_session": usage.get("cout_session", ""), "contexte_tour": context,
        "outils_appels": tools_used.get("appels", ""), "outils_car": tools_used.get("car", ""),
        "outils_detail": json.dumps(tools_used.get("detail") or {}, ensure_ascii=False) if tools_used else "",
    }
    try:
        os.makedirs(os.path.dirname(TOKEN_USAGE_CSV), exist_ok=True)
        is_new = not os.path.exists(TOKEN_USAGE_CSV)
        if not is_new:
            with open(TOKEN_USAGE_CSV, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                old_rows = list(reader) if reader.fieldnames != TOKEN_USAGE_FIELDS else None
            if old_rows is not None:
                # Fichier d'une version précédente (sans colonne effort) : réécrit avec l'en-tête actuel
                with open(TOKEN_USAGE_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=TOKEN_USAGE_FIELDS, delimiter=";", extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(old_rows)
        with open(TOKEN_USAGE_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TOKEN_USAGE_FIELDS, delimiter=";")
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except OSError as e:
        print(f"[TOKENS] ⚠️ Écriture de {TOKEN_USAGE_CSV} impossible ({e})")


def share_knowledge(body: str, projet: str, doc_type: str, sujet: str, **fields) -> dict:
    """
    Dépose une analyse dans le répertoire partagé et affiche le résultat ({} si la fonction est désactivée ou le
    texte vide). Ni un partage injoignable ni un refus (secret détecté) n'interrompent l'étape.
    """
    if not knowledge_tools.enabled() or not (body or "").strip():
        return {}
    result = knowledge_tools.publish_knowledge(body, projet, doc_type, sujet, **fields)
    print(knowledge_tools.publish_line(result))
    return result


def deleguer(nom: str, argv: list) -> int:
    """
    Relance la CLI de l'agent `nom` (main.py de AGENT_<NOM>_DIR, défaut : dépôt agent-<nom> à côté de AGENT_DATA_DIR)
    avec les mêmes arguments ; renvoie son code retour.
    """
    variable = "AGENT_" + re.sub(r"\W", "_", nom).upper() + "_DIR"
    dossier = os.getenv(variable, "").strip() or os.path.join(os.path.dirname(DATA_DIR), f"agent-{nom}")
    script = os.path.join(dossier, "main.py")
    if not os.path.exists(script):
        print(f"[DÉLÉGATION] ❌ {script} introuvable : renseigner {variable} (dépôt agent-{nom}).")
        return 2
    return subprocess.call([sys.executable, script, *argv])
