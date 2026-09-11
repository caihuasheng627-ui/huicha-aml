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


def test_export_is_draft_not_filing(client):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    r = client.get("/api/alerts/ALT-B-20260910/export")
    assert r.status_code == 200
    text = r.text
    assert "非报送报文" in text
    assert "须调查员签发" in text
