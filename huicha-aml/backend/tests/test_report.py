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
    """法规依据要能在前端展开核对，正文与生效日不能缺。"""
    from app.agents import regulation_cites
    from app.knowledge import search_knowledge

    hits = search_knowledge("可疑交易报告要素 排除理由 人工签发", kind="regulation", top_k=3)
    assert hits
    cites = [c.model_dump() for c in regulation_cites(hits, "2026-09-10")]
    assert len(cites) == len(hits)
    for cite in cites:
        assert cite["regulation_id"].startswith("KB-")
        assert cite["evidence"] and cite["source"]
        assert cite["effective_date"] and cite["as_of"] == "2026-09-10"

    fallback = [c.model_dump() for c in regulation_cites([], "2026-09-10")]
    assert len(fallback) == 1
    assert fallback[0]["regulation_id"] == ""
    assert "未检索到" in fallback[0]["title"]


def test_export_is_draft_not_filing(client, auth_headers):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    r = client.get("/api/alerts/ALT-B-20260910/export", headers=auth_headers)
    assert r.status_code == 200
    text = r.text
    assert "非报送报文" in text
    assert "须调查员签发" in text
    assert "否（本文件仅为草稿）" in text
    assert "风险等级" in text
    assert "进模脱敏" in text


from tests.conftest import dual_confirm


def test_export_reflects_human_sign(client, auth_headers):
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    ok, _ = dual_confirm(client, "ALT-A-20260910", note="同意排除")
    assert ok.status_code == 200
    text = client.get("/api/alerts/ALT-A-20260910/export", headers=auth_headers).text
    assert "已记录签发" in text
    assert "同意排除" in text
    assert "李审（002201）" in text
    assert "陈析" in text
    assert "否（本文件仅为草稿）" not in text
    assert "CLOSE" in text or "排除" in text


def test_apply_abstain_tone_rewrites_conclusion_section():
    from app.report_draft import apply_abstain_tone

    report = {
        "reason": "疑点分析认为资金或行为特征与客户身份不匹配，建议按内部规程复核后提交可疑交易报告。",
        "full_text": "【资金交易及客户行为】流水摘要。\n【结论与理由】建议上报。疑点分析认为资金或行为特征与客户身份不匹配，建议按内部规程复核后提交可疑交易报告。",
        "elements": [{"key": "可疑/排除理由", "value": "建议上报"}],
    }
    apply_abstain_tone(report, "suggest_report")
    assert "未形成可直接签发结论" in report["reason"]
    assert "建议按内部规程复核后提交可疑交易报告" not in report["reason"]
    line = next(item for item in report["full_text"].split("\n") if item.startswith("【结论与理由】"))
    assert line.startswith("【结论与理由】AI 倾向、未形成可直接签发结论。")
    assert report["elements"][0]["value"] == report["reason"]
