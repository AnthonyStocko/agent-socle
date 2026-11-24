"""
Fonctions communes des IHM d'agents, extraites telles quelles d'app.py d'agent-scrum-master : lancement de main.py
avec journal technique et journal conservé de l'exécution, phrases et cause d'interruption tirées de la sortie.
Les chemins des journaux sont lus à chaque appel (AGENT_JOURNAL_PATH, AGENT_RUN_LOGS_DIR, défaut sous AGENT_DATA_DIR).
"""
import os
import re
import subprocess
import time

import streamlit as st

from agent_socle import auth_tools
from agent_socle.jira_tools import fetch_tickets_data, parse_issue_keys
from agent_socle.chemins import DATA_DIR

# Préfixe des problèmes d'environnement rédigés par main.py (contrôle avant tout lot)
CUCUMBER_ENV_PREFIX = "[CUCUMBER ENVIRONNEMENT] ❌"
JOURNAL_MAX_BYTES = 5_000_000


def journal_path() -> str:
    """Journal technique : AGENT_JOURNAL_PATH, sinon .tmp/journal_technique.log de AGENT_DATA_DIR."""
    return os.getenv("AGENT_JOURNAL_PATH") or os.path.join(DATA_DIR, ".tmp", "journal_technique.log")


def run_logs_dir() -> str:
    """Journal conservé de chaque exécution : AGENT_RUN_LOGS_DIR, sinon .tmp/logs de AGENT_DATA_DIR."""
    return os.getenv("AGENT_RUN_LOGS_DIR") or os.path.join(DATA_DIR, ".tmp", "logs")


def run_log_path(cmd: list) -> str:
    """Journal d'une exécution de main.py : .tmp/logs/<AAAA-MM-JJ_HHMMSS>_<étape>.log."""
    step = cmd[cmd.index("--step") + 1] if "--step" in cmd and cmd.index("--step") + 1 < len(cmd) else "main"
    return os.path.join(run_logs_dir(), f"{time.strftime('%Y-%m-%d_%H%M%S')}_{re.sub(r'[^\w.-]', '_', step)}.log")


def run_main_step(cmd: list, on_line=None, quiet: bool = True) -> int:
    """
    Lance main.py (`on_line` : appelé à chaque ligne). Toute la sortie va dans le journal technique
    (.tmp/journal_technique.log, panneau « Journal technique » replié de l'en-tête) et dans le journal conservé de
    l'exécution (.tmp/logs/<date>_<étape>.log) ; par défaut (`quiet`), rien de
    brut n'est affiché : seul un indicateur d'avancement, et la dernière exécution est gardée pour en tirer des
    phrases (journal_phrases). `quiet=False` réservé au diagnostic. Renvoie le code retour.
    """
    os.makedirs(os.path.dirname(journal_path()), exist_ok=True)
    if os.path.exists(journal_path()) and os.path.getsize(journal_path()) > JOURNAL_MAX_BYTES:
        os.replace(journal_path(), journal_path() + ".1")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        # Auteur connecté (AGENT_AUTH) transmis à l'exécution : décisions, bilans et connaissances le tracent
        env={**auth_tools.subprocess_env(), "PYTHONIOENCODING": "utf-8"},
    )
    output_container = st.empty() if not quiet else None
    spinner = st.spinner("Traitement en cours… (sortie détaillée : « Journal technique »)") \
        if quiet else None
    if spinner:
        spinner.__enter__()
    logs, lines = "", []
    os.makedirs(run_logs_dir(), exist_ok=True)
    log_path = run_log_path(cmd)
    st.session_state["last_run_log"] = log_path
    with open(journal_path(), "a", encoding="utf-8") as journal, open(log_path, "w", encoding="utf-8") as run_log:
        journal.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} — {' '.join(cmd[1:])[:300]}\n")
        run_log.write(f"===== {' '.join(cmd[1:])[:300]}\n")
        author = auth_tools.current_author()
        if author:
            journal.write(f"===== lancé par {author}\n")
            run_log.write(f"===== lancé par {author}\n")
        for line in process.stdout:
            journal.write(line)
            run_log.write(line)
            run_log.flush()
            lines.append(line.rstrip("\n"))
            if output_container is not None:
                logs += line
                output_container.code(logs, language="text")
            if on_line:
                on_line(line)
        process.wait()
        journal.write(f"===== code retour {process.returncode} — journal de l'exécution : {log_path}\n")
        run_log.write(f"===== code retour {process.returncode}\n")
    if spinner:
        spinner.__exit__(None, None, None)
    st.session_state["last_run_lines"] = lines
    return process.returncode


def journal_phrases(prefix: str) -> list:
    """Phrases rédigées par main.py dans la dernière exécution, sous un préfixe (ex. problèmes d'environnement)."""
    return [line.split(prefix, 1)[1].strip() for line in st.session_state.get("last_run_lines") or []
            if prefix in line]


def interruption_cause(returncode: int) -> str:
    """Cause d'une interruption, en une phrase : problème d'environnement, sinon dernière erreur signalée."""
    environment = journal_phrases(CUCUMBER_ENV_PREFIX)
    if environment:
        return environment[0]
    errors = [re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", line).replace("❌", "").replace("⛔", "").strip()
              for line in st.session_state.get("last_run_lines") or [] if "❌" in line or "⛔" in line]
    errors = [e for e in errors if e and not e.startswith(("Traceback", "File "))]
    return (errors[-1][:240] if errors else
            f"le traitement s'est arrêté avant la fin (code retour {returncode}), voir le journal technique")


def render_technical_journal() -> None:
    """Panneau « Journal technique », replié : sortie brute des traitements (jamais dans une carte)."""
    with st.expander("Journal technique", icon=":material/terminal:"):
        if not os.path.exists(journal_path()):
            st.caption("Aucun traitement lancé pour l'instant.")
            return
        with open(journal_path(), "r", encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-400:]
        st.caption(f"Sortie brute des derniers traitements (400 dernières lignes) — {journal_path()} ; journal "
                   f"conservé de chaque exécution dans {run_logs_dir()}"
                   + (f" (dernière : {st.session_state['last_run_log']})" if st.session_state.get("last_run_log")
                      else ""))
        st.code("".join(tail), language="text")


def search_criteria_form(key_prefix: str) -> dict:
    """Critères de recherche Jira, mêmes champs et valeurs par défaut dans les onglets Lancement et Intégration."""
    # Accès direct par lien ou clé : prioritaire sur tous les autres critères
    issue_keys = parse_issue_keys(st.text_input(
        "Lien(s) ou clé(s) Jira (optionnel) :",
        key=f"{key_prefix}search_links",
        placeholder="https://…/browse/PROJ-123, PROJ-456",
        help="Collez un ou plusieurs liens de tickets Jira (ou leurs clés), séparés par des virgules ou des espaces. "
             "S'il est renseigné, les critères ci-dessous (projet, équipe, statuts, labels) sont ignorés."
    ))
    if issue_keys:
        st.caption("Recherche directe : " + ", ".join(issue_keys) + " — les autres critères sont ignorés.")

    # Recherche rapide « épopées ouvertes de l'équipe » (onglet Configuration)
    open_epics_team = os.getenv("JIRA_OPEN_EPICS_TEAM", "").strip()
    open_epics_status = os.getenv("JIRA_OPEN_EPICS_STATUS", "").strip()
    open_epics_only = st.checkbox(
        f"Épopées au statut « {open_epics_status} » de l'équipe {open_epics_team}"
        if open_epics_team and open_epics_status else "Épopées ouvertes de mon équipe",
        key=f"{key_prefix}open_epics_only",
        disabled=not (open_epics_team and open_epics_status) or bool(issue_keys),
        help="Si coché, la recherche porte sur les épopées du projet cible à ce statut pour cette équipe : "
             "les critères Équipe, Statuts et Labels ci-dessous sont ignorés. "
             "Équipe et statut : JIRA_OPEN_EPICS_TEAM et JIRA_OPEN_EPICS_STATUS (onglet Configuration)."
    ) and bool(open_epics_team and open_epics_status) and not issue_keys
    disable_filters = open_epics_only or bool(issue_keys)

    # Valeurs par défaut du .env posées une fois : la saisie est gardée quand on change de page (PERSISTENT_KEYS)
    for name, env_name in (("search_project", "JIRA_PROJECT_KEY"), ("search_team", "JIRA_SEARCH_TEAM"),
                           ("search_statuses", "JIRA_SEARCH_STATUSES"), ("search_labels", "JIRA_SEARCH_LABELS")):
        st.session_state.setdefault(f"{key_prefix}{name}", os.getenv(env_name, ""))
    col1, col2 = st.columns(2)
    with col1:
        jira_project_input = st.text_input(
            "Projet Jira cible :",
            key=f"{key_prefix}search_project",
            help="Clé du projet Jira (ex. PROJ).",
            disabled=bool(issue_keys)
        )
        jira_team_input = st.text_input(
            "Équipe / Composant (Optionnel) :",
            key=f"{key_prefix}search_team",
            help="Composant Jira ou équipe Atlassian (ex. WMS, Socle...)",
            disabled=disable_filters
        )

    with col2:
        jira_status_input = st.text_input(
            "États / Statuts (Séparés par une virgule) :",
            key=f"{key_prefix}search_statuses",
            help="Ex: Analysée, En cours, A traiter (laissez vide pour tous les états)",
            disabled=disable_filters
        )
        jira_label_input = st.text_input(
            "Labels (Séparés par une virgule) :",
            key=f"{key_prefix}search_labels",
            help="Ex. le label d'attente de l'équipe (laissez vide si aucun label requis)",
            disabled=disable_filters
        )

    return {
        # Recherche par lien : projet du premier ticket (repris pour la suite du traitement)
        "project_key": issue_keys[0].rsplit("-", 1)[0] if issue_keys else jira_project_input.strip().upper(),
        "issue_keys": issue_keys,
        "statuses": [s.strip() for s in jira_status_input.split(",") if s.strip()],
        "labels": [l.strip() for l in jira_label_input.split(",") if l.strip()],
        "team": jira_team_input.strip(),
        "open_epics_only": open_epics_only,
        "open_epics_team": open_epics_team,
        "open_epics_status": open_epics_status,
    }


def search_jira_tickets(criteria: dict) -> list:
    """Tickets correspondant aux critères de search_criteria_form. Lève JiraSearchError."""
    if criteria.get("issue_keys"):
        return fetch_tickets_data(project_key=criteria["project_key"], issue_keys=criteria["issue_keys"])
    if criteria["open_epics_only"]:
        return fetch_tickets_data(
            project_key=criteria["project_key"],
            statuses=[criteria["open_epics_status"]],
            epics_only=True,
            atlassian_team=criteria["open_epics_team"]
        )
    return fetch_tickets_data(
        project_key=criteria["project_key"],
        statuses=criteria["statuses"],
        labels=criteria["labels"],
        team=criteria["team"]
    )
