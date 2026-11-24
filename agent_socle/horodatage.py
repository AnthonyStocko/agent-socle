"""Horodatages des rapports Cucumber (extrait de tools/cucumber_verify.py, inchangé)."""
from datetime import datetime, timezone


def _timestamp(value) -> datetime:
    """Horodatage ISO d'un rapport Cucumber (start_timestamp), en UTC ; None s'il est absent ou illisible."""
    try:
        stamp = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)

