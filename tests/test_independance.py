"""Le socle n'importe aucun agent : seulement la bibliothèque standard, ses dépendances et lui-même."""
import ast
from pathlib import Path

PAQUET = Path(__file__).resolve().parent.parent / "agent_socle"
INTERDITS = ("tools", "main", "app", "webhook_server", "mcp_lecture")


def test_aucun_import_d_agent():
    fautes = []
    for f in sorted(PAQUET.glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            noms = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module or ""] if isinstance(n, ast.ImportFrom) else []
            fautes += [f"{f.name}:{n.lineno} {nom}" for nom in noms if nom.split(".")[0] in INTERDITS]
    assert not fautes, fautes
