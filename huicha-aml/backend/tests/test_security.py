from app.knowledge import corpus_size, search_knowledge
from app.security import cors_origins


def test_cors_default_is_not_wildcard():
    origins = cors_origins()
    assert origins
    assert "*" not in origins


def test_cors_header_allows_localhost(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_header_rejects_unknown_origin(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in {None, ""}


def test_demo_token_guard(client, monkeypatch):
    monkeypatch.setenv("HUICHA_DEMO_TOKEN", "demo-secret")
    blocked = client.get("/api/alerts")
    assert blocked.status_code == 401
    ok = client.get("/api/alerts", headers={"X-Huicha-Token": "demo-secret"})
    assert ok.status_code == 200
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["auth"] == "demo_token"


def test_export_rejects_query_token(client, monkeypatch):
    monkeypatch.setenv("HUICHA_DEMO_TOKEN", "demo-secret")
    client.post(
        "/api/alerts/ALT-B-20260910/investigate",
        params={"use_challenger": True},
        headers={"X-Huicha-Token": "demo-secret"},
    )
    blocked = client.get("/api/alerts/ALT-B-20260910/export")
    assert blocked.status_code == 401
    via_query = client.get("/api/alerts/ALT-B-20260910/export?token=demo-secret")
    assert via_query.status_code == 401
    ok = client.get("/api/alerts/ALT-B-20260910/export", headers={"X-Huicha-Token": "demo-secret"})
    assert ok.status_code == 200
    assert "规则分" in ok.text
    assert "非校准置信度" in ok.text


def test_knowledge_is_small_keyword_corpus():
    assert 15 <= corpus_size() <= 40
    hits = search_knowledge("拆分存入 阈值", kind="typology", top_k=3)
    assert hits
    assert hits[0]["id"].startswith("KB-")
