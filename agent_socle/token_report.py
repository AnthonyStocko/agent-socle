"""
Rapport de consommation (0 token) à partir de .tmp/token_usage.csv : où partent le coût et le contexte.

    .venv\\Scripts\\python.exe -m tools.token_report [--depuis 2026-11-19] [--ticket ODA-123] [--etape cucumber]

- par étape : appels, coût, part du coût, contexte moyen relu par tour, part des appels en reprise (--resume) ;
- par outil : résultats renvoyés (nombre, caractères), d'après la colonne outils_detail ;
- appels les plus chers.

Les lignes antérieures à la mesure du contexte (colonnes vides) comptent dans le coût, pas dans le contexte.
"""
from agent_socle.chemins import DATA_DIR
import argparse
import csv
import json
import os
import sys

WORKSPACE_DIR = DATA_DIR
CSV_FILE = os.path.join(WORKSPACE_DIR, ".tmp", "token_usage.csv")


def _num(value) -> float:
    try:
        return float(str(value).replace(",", ".")) if value not in ("", None) else 0.0
    except ValueError:
        return 0.0


def read_rows(path: str = CSV_FILE, since: str = "", ticket: str = "", step: str = "") -> list:
    """Lignes du CSV filtrées (date ≥ since, ticket exact, étape commençant par step)."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    return [r for r in rows
            if (not since or (r.get("date") or "") >= since)
            and (not ticket or (r.get("ticket") or "").upper() == ticket.upper())
            and (not step or (r.get("etape") or "").startswith(step))]


def summarize(rows: list) -> dict:
    """{"total", "etapes": {etape: {...}}, "outils": {outil: [appels, car]}, "plus_chers": [...]}."""
    total = sum(_num(r.get("cout_usd")) for r in rows)
    steps, tools = {}, {}
    for r in rows:
        s = steps.setdefault(r.get("etape") or "?", {"appels": 0, "cout": 0.0, "contexte": [], "reprises": 0})
        s["appels"] += 1
        s["cout"] += _num(r.get("cout_usd"))
        if _num(r.get("contexte_tour")):
            s["contexte"].append(_num(r.get("contexte_tour")))
        s["reprises"] += (r.get("reprise") == "oui")
        try:
            detail = json.loads(r.get("outils_detail") or "{}")
        except ValueError:
            detail = {}
        for name, value in (detail.items() if isinstance(detail, dict) else []):
            if isinstance(value, list) and len(value) == 2:
                calls, chars = tools.get(name, [0, 0])
                tools[name] = [calls + int(_num(value[0])), chars + int(_num(value[1]))]
    for s in steps.values():
        values = s.pop("contexte")
        s["contexte_moyen"] = round(sum(values) / len(values)) if values else 0
        s["part"] = round(100 * s["cout"] / total, 1) if total else 0.0
    return {"total": total, "appels": len(rows),
            "etapes": dict(sorted(steps.items(), key=lambda kv: -kv[1]["cout"])),
            "outils": dict(sorted(tools.items(), key=lambda kv: -kv[1][1])),
            "plus_chers": sorted(rows, key=lambda r: -_num(r.get("cout_usd")))[:5]}


def render(summary: dict) -> str:
    lines = [f"{summary['appels']} appel(s), coût total {summary['total']:.2f} $", "", "Par étape :"]
    for name, s in summary["etapes"].items():
        context = f"{round(s['contexte_moyen'] / 1000)}k/tour" if s["contexte_moyen"] else "contexte ?"
        lines.append(f"  {name:<28} {s['appels']:>4} appel(s) {s['cout']:>8.2f} $ {s['part']:>5.1f} % "
                     f"{context:>12}  reprises {s['reprises']}")
    if summary["outils"]:
        lines += ["", "Résultats d'outils (relus ensuite à chaque tour) :"]
        total_chars = sum(v[1] for v in summary["outils"].values()) or 1
        for name, (calls, chars) in list(summary["outils"].items())[:12]:
            lines.append(f"  {name:<28} {calls:>5} résultat(s) {round(chars / 1000):>7}k car. "
                         f"{round(100 * chars / total_chars, 1):>5.1f} %")
    if summary["plus_chers"]:
        lines += ["", "Appels les plus chers :"]
        for r in summary["plus_chers"]:
            lines.append(f"  {r.get('date', '')} {r.get('ticket', ''):<12} {r.get('etape', ''):<24} "
                         f"{_num(r.get('cout_usd')):.2f} $ tours {r.get('tours', '')} reprise {r.get('reprise') or '?'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rapport de consommation des appels Claude (token_usage.csv)")
    parser.add_argument("--depuis", default="", help="date de début (AAAA-MM-JJ)")
    parser.add_argument("--ticket", default="")
    parser.add_argument("--etape", default="", help="préfixe d'étape (ex. cucumber)")
    parser.add_argument("--fichier", default=CSV_FILE)
    args = parser.parse_args(argv)
    rows = read_rows(args.fichier, args.depuis, args.ticket, args.etape)
    if not rows:
        print(f"Aucune ligne dans {args.fichier} pour ces critères.")
        return 1
    print(render(summarize(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
