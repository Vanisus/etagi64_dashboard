import json
import os
from datetime import timedelta
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.application import app
from app.auth.backend import current_admin
from app.config.settings import Settings
from app.db.session import engine
from app.services import statistics_collector as collector
from app.services.metrics import yesterday
from app.services.wordstat_client import WordStatClient

pytestmark = pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Нужна отдельная мигрированная тестовая БД")
HEADERS = {"Origin": "http://localhost:5173"}


@pytest.fixture
def api():
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE daily_query_metrics, query_results, collection_runs, search_queries, categories CASCADE"))
        connection.execute(text("DELETE FROM cities WHERE id = 'test'"))
    app.dependency_overrides[current_admin] = lambda: object()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def seed(api):
    assert api.post("/api/categories", headers=HEADERS, json={"id": "buy", "name": "Купить"}).status_code == 201
    for qid in ("q1", "q2"):
        assert api.post("/api/queries", headers=HEADERS, json={
            "id": qid, "category_id": "buy", "city_id": "saratov", "phrase": qid,
        }).status_code == 201


def mock_client(monkeypatch, handler):
    monkeypatch.setattr(collector, "load_settings", lambda: Settings("test", "test"))
    monkeypatch.setattr(collector, "WordStatClient", lambda *args, **kw: WordStatClient(
        *args, transport=httpx.MockTransport(handler), min_interval=0))
    monkeypatch.setattr("app.services.wordstat_client.time.sleep", lambda _: None)


def test_daily_flow(api, monkeypatch):
    seed(api)
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        counts = (100, 120) if body["phrase"] == "q1" else (50, 40)
        return httpx.Response(200, json={"results": [
            {"date": f"{yesterday()-timedelta(days=1)}T00:00:00Z", "count": str(counts[0])},
            {"date": f"{yesterday()}T00:00:00Z", "count": str(counts[1])},
        ]})

    mock_client(monkeypatch, handler)
    response = api.post("/api/collections", headers=HEADERS, json={"city_id": "saratov", "method": "dynamics"})
    assert response.status_code == 202, response.text
    assert api.post("/api/collections", headers=HEADERS, json={"city_id": "saratov", "method": "dynamics"}).status_code == 409
    run = collector.claim_next_run()
    collector.collect_run(run)
    result = api.get("/api/statistics/daily", params={"city_id": "saratov", "limit": 1}).json()
    assert result["comparison_status"] == "complete" and result["total"] == 2
    assert len(result["items"]) == 1
    assert result["items"][0]["delta_percent"] == 20
    assert result["categories"][0]["current_total"] == 160
    assert result["categories"][0]["delta"] == 10
    assert all(body["regions"] == ["194"] for body in seen)
    results = api.get(f"/api/collections/{run}/results", params={"limit": 1}).json()
    assert results["total"] == 2 and len(results["items"]) == 1
    assert "raw_response" not in results["items"][0]
    assert "raw_response" in api.get(f"/api/collections/{run}/results?include_raw=true").json()["items"][0]
    api.patch("/api/queries/q2", headers=HEADERS, json={"phrase": "изменено"})
    changed = api.get("/api/statistics/daily?city_id=saratov").json()
    assert changed["comparison_status"] == "partial"
    assert changed["categories"][0]["current_total"] is None
    assert api.get("/api/statistics/daily?city_id=engels").json()["comparison_status"] == "no_data"


def test_partial_response_is_not_zero(api, monkeypatch):
    seed(api)
    mock_client(monkeypatch, lambda request: httpx.Response(200, json={"results": []}))
    response = api.post("/api/collections", headers=HEADERS, json={"city_id": "saratov", "method": "dynamics"})
    run = collector.claim_next_run()
    collector.collect_run(run)
    assert api.get(f"/api/collections/{run}").json()["status"] == "failed"
    assert api.get("/api/statistics/daily?city_id=saratov").json()["comparison_status"] == "no_data"
    assert response.status_code == 202


def test_continues_after_phrase_error(api, monkeypatch):
    seed(api)
    mock_client(monkeypatch, lambda request: httpx.Response(
        400 if json.loads(request.content)["phrase"] == "q1" else 200, json={"totalCount": "321"}))
    api.post("/api/collections", headers=HEADERS, json={"city_id": "saratov"})
    run = collector.claim_next_run()
    collector.collect_run(run)
    items = api.get(f"/api/collections/{run}/results").json()["items"]
    assert [i["status"] for i in items] == ["error", "ok"]


def test_top_dashboard_and_region(api, monkeypatch):
    seed(api)
    mock_client(monkeypatch, lambda request: httpx.Response(200, json={"totalCount": "321"}))
    api.post("/api/collections", headers=HEADERS, json={"city_id": "saratov"})
    collector.collect_run(collector.claim_next_run())
    result = api.get("/api/dashboard/categories?city_id=saratov").json()
    assert result["has_data"] and result["region_id"] == "194"
    assert result["items"][0]["average_frequency"] == 321
    assert api.get("/api/dashboard/categories?city_id=saratov&region_id=213").json()["has_data"] is False


def test_city_and_security(api):
    assert api.post("/api/cities", json={"id": "test", "name": "Тест"}).status_code == 403
    assert api.post("/api/cities", headers=HEADERS, json={"id": "test", "name": "Тест"}).status_code == 201
    assert api.post("/api/collections", headers=HEADERS, json={"city_id": "test"}).status_code == 422
    assert api.patch("/api/cities/test", headers=HEADERS, json={"yandex_region_id": "213"}).status_code == 200
    assert api.patch("/api/cities/test", headers=HEADERS, json={"name": None}).status_code == 422
    assert api.get("/api/ready").status_code == 200
    app.dependency_overrides.clear()
    assert api.get("/api/statistics/daily?city_id=saratov").status_code == 401


def test_stop_marks_interrupted(api, monkeypatch):
    seed(api)
    mock_client(monkeypatch, lambda _: httpx.Response(200, json={"totalCount": "1"}))
    api.post("/api/collections", headers=HEADERS, json={"city_id": "saratov"})
    run = collector.claim_next_run()
    stop = Event()
    stop.set()
    collector.collect_run(run, stop_event=stop)
    assert api.get(f"/api/collections/{run}").json()["status"] == "interrupted"
