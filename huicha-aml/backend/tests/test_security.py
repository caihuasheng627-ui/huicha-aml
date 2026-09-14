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
    from app.knowledge import retrieval_mode, search_unit_count

    assert 30 <= corpus_size() <= 80
    assert search_unit_count() > corpus_size()
    assert retrieval_mode() == "hybrid-keyword-tfidf"
    hits = search_knowledge("拆分存入 阈值", kind="typology", top_k=3)
    assert hits
    assert hits[0]["id"].startswith("KB-")
    assert hits[0].get("body")
    assert "score_vector" in hits[0]
    law = search_knowledge("反洗钱法 受益所有人 尽职调查", kind="regulation", top_k=5)
    assert law
    assert any(
        h["id"].startswith("KB-AML-") or h["id"].startswith("KB-CDD-") or h["id"].startswith("KB-UBO-") for h in law
    )
    aml = next(h for h in search_knowledge("反洗钱法 总则 第一条", kind="regulation", top_k=8) if h["parent_id"] == "KB-AML-01")
    assert aml["effective_date"] == "2025-01-01"
    assert aml["data_note"] == "official-statute"
    assert "第一条" in aml["body"]
    liability = next(
        h for h in search_knowledge("法律责任 拆分交易 第五十二条", kind="regulation", top_k=8) if h["parent_id"] == "KB-AML-06"
    )
    assert "第五十二条" in liability["body"]
    assert "（九）" in liability["body"]
    cdd = next(h for h in search_knowledge("尽职调查 了解你的客户", kind="regulation", top_k=8) if h["parent_id"] == "KB-CDD-01")
    assert cdd["effective_date"] == "2026-01-01"
    ubo = next(h for h in search_knowledge("受益所有人 百分之二十五", kind="regulation", top_k=8) if h["parent_id"] == "KB-UBO-02")
    assert ubo["effective_date"] == "2026-01-20"
    ctr = next(h for h in search_knowledge("人工分析 排除理由 第十四条", kind="regulation", top_k=8) if h["id"] == "KB-CTR-03-a14")
    assert ctr["effective_date"] == "2025-12-01"
    assert ctr["chunk_kind"] == "article"
    assert len(ctr["snippet"]) <= len(ctr["body"])


def test_kb_doc_api_returns_full_article(client):
    r = client.get("/api/kb/KB-REG-01")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == "KB-REG-01"
    assert data["title"]
    assert data["body"]
    assert data["source"]
    aml = client.get("/api/kb/KB-AML-06")
    assert aml.status_code == 200
    body = aml.json()
    assert body["data_note"] == "official-statute"
    assert "第五十三条" in body["body"]
    assert len(body["body"]) > 500
    chunk = client.get("/api/kb/KB-CTR-03-a14")
    assert chunk.status_code == 200
    art = chunk.json()
    assert art["id"] == "KB-CTR-03-a14"
    assert art["parent_id"] == "KB-CTR-03"
    assert art["article"] == "第十四条"
    assert "人工分析" in art["body"]
    missing = client.get("/api/kb/KB-NOPE")
    assert missing.status_code == 404
