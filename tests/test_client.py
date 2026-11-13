import json
from datetime import date

import httpx
import pytest

from app.services.wordstat_client import WordStatAPIError, WordStatClient


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.services.wordstat_client.time.sleep", lambda _: None)


def client(handler):
    return WordStatClient("test", "test", transport=httpx.MockTransport(handler), min_interval=0)


def test_path_and_regions():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": []})

    with client(handler) as api:
        api.dynamics("дом", date(2026, 11, 11), date(2026, 11, 12), regions=["194"])
    assert calls[0].url.path == "/v2/wordstat/dynamics"
    assert json.loads(calls[0].content)["regions"] == ["194"]


def test_retry_transient():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503 if len(calls) < 3 else 200, json={})

    with client(handler) as api:
        api.top_requests("дом")
    assert len(calls) == 3


def test_auth_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"message": "unauthorized"})

    with client(handler) as api, pytest.raises(WordStatAPIError):
        api.top_requests("дом")
    assert len(calls) == 1


@pytest.mark.parametrize("region", ["0", "-1", "abc", "١٢"])
def test_bad_region(region):
    with client(lambda _: httpx.Response(200, json={})) as api, pytest.raises(ValueError):
        api.top_requests("дом", regions=[region])
