def test_report_binds_evidence_and_regulation(client):
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    data = r.json()
    sr = data["structured_report"]
    for key in (
        "case_overview",
        "customer_profile",
        "transaction_summary",
        "suspicious_patterns",
        "evidence_ids",
        "risk_assessment",
        "challenger_review",
        "regulation_basis",
        "recommendation",
        "human_review",
    ):
        assert key in sr
    assert sr["data_note"] == "synthetic"
    assert sr["recommendation"] != "REPORT"
    cites = sr["regulation_basis"]
    assert cites
    if cites[0]["regulation_id"]:
        assert cites[0]["source"]
    else:
        assert "未检索到" in cites[0]["title"]
    assert "须" in sr["human_review"] or "人工" in sr["human_review"]


def test_regulation_cites_carry_paraphrase_for_review():
    """法规依据要能在前端展开核对，转述正文与生效日不能缺。"""
    from app.agents import regulation_cites
    from app.knowledge import search_knowledge

    hits = search_knowledge("可疑交易报告要素 排除理由 人工签发", kind="regulation", top_k=3)
    assert hits
    cites = [c.model_dump() for c in regulation_cites(hits, "2026-09-10")]
    assert len(cites) == len(hits)
    for cite, hit in zip(cites, hits):
        assert cite["regulation_id"].startswith("KB-REG-")
        assert cite["evidence"] and cite["source"]
        assert cite["effective_date"] == hit["effective_date"]
        assert cite["as_of"] == "2026-09-10"
        assert cite["version"] == hit["version"]

    fallback = [c.model_dump() for c in regulation_cites([], "2026-09-10")]
    assert len(fallback) == 1
    assert fallback[0]["regulation_id"] == ""
    assert "未检索到" in fallback[0]["title"]


def test_clause_effective_date_excludes_pre_effective_as_of():
    """案发日早于某条款生效日时，该条不得被检索/引用。"""
    from app.agents import regulation_cites
    from app.knowledge import list_knowledge, search_knowledge

    meta = {d["id"]: d for d in list_knowledge()}
    assert meta["KB-REG-04"]["effective_date"] == "2021-03-01"
    assert meta["KB-REG-01"]["effective_date"] == "2017-01-01"

    before = search_knowledge("补正 五日 要素不全", kind="regulation", top_k=8, as_of="2019-06-01")
    assert all(h["id"] != "KB-REG-04" for h in before)

    after = search_knowledge("补正 五日 要素不全", kind="regulation", top_k=8, as_of="2022-01-01")
    assert any(h["id"] == "KB-REG-04" for h in after)
    hit = next(h for h in after if h["id"] == "KB-REG-04")
    assert hit["effective_date"] == "2021-03-01"
    assert hit["as_of"] == "2022-01-01"

    cites = [c.model_dump() for c in regulation_cites(before, "2019-06-01")]
    assert all(c["regulation_id"] != "KB-REG-04" for c in cites)


def test_export_is_draft_not_filing(client):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    r = client.get("/api/alerts/ALT-B-20260910/export")
    assert r.status_code == 200
    text = r.text
    assert "非报送报文" in text
    assert "须调查员签发" in text
    assert "否（本文件仅为草稿）" in text
    assert "风险等级" in text


def test_export_reflects_human_sign(client, auth_headers):
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    ok = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": "同意排除"},
        headers=auth_headers,
    )
    assert ok.status_code == 200
    text = client.get("/api/alerts/ALT-A-20260910/export").text
    assert "已记录签发" in text
    assert "同意排除" in text
    assert "陈析（002183）" in text
    assert "否（本文件仅为草稿）" not in text
    assert "CLOSE" in text or "排除" in text
