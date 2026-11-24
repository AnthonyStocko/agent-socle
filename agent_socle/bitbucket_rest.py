"""
Base REST de Bitbucket Data Center (API 1.0), extraite telle quelle de tools/pr_review.py d'agent-scrum-master :
adresse, en-têtes du jeton (BITBUCKET_URL, BITBUCKET_HTTP_TOKEN), lecture paginée, création de pull request.
"""
import os

import requests


class BitbucketError(RuntimeError):
    pass


def base_url() -> str:
    return os.getenv("BITBUCKET_URL", "").strip().rstrip("/")


def _headers() -> dict:
    token = os.getenv("BITBUCKET_HTTP_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"} if token else {"Accept": "application/json"}


def configured() -> bool:
    return bool(base_url() and os.getenv("BITBUCKET_HTTP_TOKEN", "").strip())


def _get(path: str, params: dict = None, raw: bool = False):
    if not base_url():
        raise BitbucketError("BITBUCKET_URL non renseigné (onglet Configuration)")
    try:
        response = requests.get(f"{base_url()}{path}", headers=_headers(), params=params or {}, timeout=30)
    except requests.RequestException as e:
        raise BitbucketError(f"Bitbucket injoignable : {type(e).__name__}") from e
    if response.status_code == 401:
        raise BitbucketError("Bitbucket refuse le jeton (HTTP 401) : vérifie BITBUCKET_HTTP_TOKEN")
    if response.status_code != 200:
        raise BitbucketError(f"Bitbucket a répondu HTTP {response.status_code} : {response.text[:200]}")
    return response.text if raw else response.json()


def _paged(path: str, params: dict = None, limit: int = 200) -> list:
    values, start = [], 0
    while len(values) < limit:
        page = _get(path, {**(params or {}), "start": start, "limit": min(100, limit - len(values))})
        values += page.get("values") or []
        if page.get("isLastPage", True) or "nextPageStart" not in page:
            break
        start = page["nextPageStart"]
    return values


def create_pull_request(project: str, repo: str, payload: dict) -> str:
    """
    Ouvre une PR (création seule : jamais d'approbation ni de fusion par l'agent) et renvoie son adresse. PR déjà
    ouverte pour la même branche : son adresse. Lève BitbucketError.
    """
    if not configured():
        raise BitbucketError("BITBUCKET_URL ou BITBUCKET_HTTP_TOKEN non renseigné (onglet Configuration)")
    path = f"/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests"
    try:
        response = requests.post(f"{base_url()}{path}", headers={**_headers(), "Content-Type": "application/json"},
                                 json=payload, timeout=30)
    except requests.RequestException as e:
        raise BitbucketError(f"Bitbucket injoignable : {type(e).__name__}") from e
    if response.status_code == 409:
        source = (payload.get("fromRef") or {}).get("id", "")
        for pr in _paged(path, {"state": "OPEN", "direction": "OUTGOING", "at": source}, limit=25):
            return ((pr.get("links") or {}).get("self") or [{}])[0].get("href", "")
        raise BitbucketError(f"PR refusée par Bitbucket (HTTP 409) : {response.text[:200]}")
    if response.status_code not in (200, 201):
        raise BitbucketError(f"PR refusée par Bitbucket (HTTP {response.status_code}) : {response.text[:200]}")
    return ((response.json().get("links") or {}).get("self") or [{}])[0].get("href", "")
