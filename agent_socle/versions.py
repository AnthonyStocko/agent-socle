"""Normalisation des numéros de version (extraite de tools/standard_version.py)."""
import re

_VERSION = re.compile(r"(?<![\d.])(\d{2})\.(\d{1,3})((?:\.\d+)*)")


def normalize(raw: str) -> tuple:
    """(« majeure.mineure », version complète) ; ('', '') si `raw` n'est pas une version (ex. development)."""
    text = (raw or "").strip()
    match = _VERSION.search(text)
    if not match:
        return "", ""
    full = match.group(0) + ("-SNAPSHOT" if "SNAPSHOT" in text.upper() else "")
    return f"{match.group(1)}.{match.group(2)}", full


def std_refs(version: str, defaults: tuple) -> tuple:
    """Références d'un dépôt du Standard pour `version` (branches et tags de version), puis `defaults`."""
    if not version or not normalize(version)[0]:
        return tuple(defaults)
    v = normalize(version)[0]
    return (f"origin/release/{v}", f"origin/v{v}", f"origin/{v}", f"v{v}", v, *defaults)
