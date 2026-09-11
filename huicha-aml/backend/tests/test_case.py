def test_case_alias_lists_alerts(client):
    a = client.get("/api/alerts")
    c = client.get("/api/cases")
    assert a.status_code == 200
    assert c.json() == a.json()
    assert any(x["id"] == "ALT-L-20260910" for x in c.json())


def test_investigate_returns_case_v2(client):
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    assert data["data_note"] == "synthetic"
    v2 = data["case_v2"]
    assert v2["case_id"] == "ALT-B-20260910"
    assert v2["recommendation"] in {"CLOSE", "MONITOR", "EDD", "REPORT_REVIEW"}
    assert v2["human_required"] is True
    assert data["investigation_plan"]["investigation_plan"]
    assert data["evidence_graph"]
    assert data["risk"]["factors"]
    assert data["structured_report"]["human_review"]
    assert data["prompt_versions"]["challenger"] == "challenger_v2"


def test_layering_demo_chain(client):
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    tx_ids = {t["id"] for t in data["transactions"]}
    assert {"TX-L-01", "TX-L-02", "TX-L-03"} <= tx_ids
    assert data["conclusion"] == "suggest_report"
    assert data["case_v2"]["recommendation"] == "REPORT_REVIEW"


def test_agent_cannot_auto_report(client):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    d = client.post("/api/alerts/ALT-B-20260910/decide", json={"decision": "confirm", "note": ""})
    assert d.status_code == 200
    body = d.json()
    assert body["final_action"] == "human_only"
    assert "自动报送" in body["note"]
