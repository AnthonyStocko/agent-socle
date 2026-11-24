"""Base REST Bitbucket : configuration requise, PR déjà ouverte (409) renvoyée par son adresse."""
import json

import pytest

from agent_socle import bitbucket_rest as bb


class _Reponse:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


def test_pr_sans_configuration(monkeypatch):
    monkeypatch.setenv("BITBUCKET_URL", "")
    with pytest.raises(bb.BitbucketError):
        bb.create_pull_request("P", "r", {})


def test_pr_deja_ouverte(monkeypatch):
    monkeypatch.setenv("BITBUCKET_URL", "https://git.example.io/")
    monkeypatch.setenv("BITBUCKET_HTTP_TOKEN", "t0k")
    monkeypatch.setattr(bb.requests, "post", lambda *a, **k: _Reponse({}, 409))
    monkeypatch.setattr(bb.requests, "get", lambda *a, **k: _Reponse(
        {"values": [{"links": {"self": [{"href": "https://git.example.io/pr/3"}]}}], "isLastPage": True}))
    assert bb.create_pull_request("P", "r", {"fromRef": {"id": "refs/heads/f"}}) == "https://git.example.io/pr/3"
    assert bb._headers()["Authorization"] == "Bearer t0k"
