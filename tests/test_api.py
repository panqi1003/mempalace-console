import os

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.reader import ReadOnlyReader, ReaderUnavailable


class FakeReader(ReadOnlyReader):
    def __init__(self):
        super().__init__(transports={"hub": lambda t, a: {"tool": t, "args": a}})

    def search(self, query, wing=None, room=None, limit=10):
        if query == "boom":
            raise ReaderUnavailable("down")
        return {"query": query, "hits": []}

    def repair_status_text(self):
        return "PALACE OK"

    def wakeup(self, wing):
        return f"wake-up --wing {wing}"

    def hub_log_tail(self, lines=50, lang="zh"):
        return "log line"

    def backups(self):
        return [{"name": "b.sqlite3", "size_bytes": 1, "mtime_iso": "2026-01-01T00:00:00"}]


@pytest.fixture()
def client():
    return TestClient(create_app(FakeReader()))


def test_overview_shape(client):
    body = client.get("/api/overview").json()
    assert body["data"]["tool"] == "mempalace_status"
    assert "tiers" in body


def test_search_endpoint(client):
    body = client.get("/api/search", params={"q": "hello"}).json()
    assert body["data"] == {"query": "hello", "hits": []}


def test_search_unavailable_maps_503(client):
    resp = client.get("/api/search", params={"q": "boom"})
    assert resp.status_code == 503
    assert resp.json()["error"]["message"] == "palace unreachable"


def test_drawers_pagination_params(client):
    body = client.get(
        "/api/drawers", params={"wing": "demo_wing", "offset": 20, "limit": 5}
    ).json()
    assert body["data"]["args"] == {"wing": "demo_wing", "offset": 20, "limit": 5}


def test_hallways_endpoint(client):
    body = client.get("/api/graph/hallways", params={"wing": "demo_wing"}).json()
    assert body["data"]["tool"] == "mempalace_list_hallways"
    assert body["data"]["args"] == {"wing": "demo_wing"}


def test_activity_endpoint(client):
    body = client.get("/api/activity", params={"days": 30}).json()
    assert body["data"]["days"] == 30
    assert "per_day" in body["data"]


def test_audit_endpoint(client):
    body = client.get("/api/audit").json()
    assert body["data"]["total"] == 0
    assert "by_ingest" in body["data"]


def test_wakeup_endpoint(client):
    body = client.get("/api/wakeup", params={"wing": "demo_wing"}).json()
    assert "wake-up" in body["data"]["text"]


def test_health_summary(client):
    body = client.get("/api/health/summary").json()
    assert body["repair_status"] == "PALACE OK"
    assert body["hub_log_tail"] == "log line"
    assert body["backups"][0]["name"] == "b.sqlite3"
    assert "palace" in body


def test_no_store_header(client):
    resp = client.get("/api/wings")
    assert resp.headers["Cache-Control"] == "no-store"


def test_index_served():
    web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
    index = os.path.join(web_dir, "index.html")
    assert os.path.exists(index), "web/index.html 应已由前端任务创建"
    resp = TestClient(create_app(FakeReader())).get("/")
    assert resp.status_code == 200
    assert "MemPalace" in resp.text
