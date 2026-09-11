def test_investigate_writes_audit_chain(client):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    d = client.get("/api/alerts/ALT-B-20260910").json()
    actions = [a["action"] for a in d["audit"]]
    assert "investigate" in actions
    assert any(a.startswith("tool:") for a in actions)
    inv_row = [a for a in d["audit"] if a["action"] == "investigate"][-1]
    assert "ALT-B-20260910" in inv_row["detail"]
    assert "prompt_versions" in inv_row["detail"] or "建议结论" in inv_row["detail"]


def test_human_decision_audited(client, auth_headers):
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    client.post("/api/alerts/ALT-A-20260910/decide", json={"decision": "confirm", "note": "人签"}, headers=auth_headers)
    d = client.get("/api/cases/ALT-A-20260910").json()
    assert d["human_decision"] == "confirm"
    assert d["signed_by_id"] == "002183"
    assert d["signed_by_name"] == "陈析"
    assert any(a["action"] == "decide" for a in d["audit"])
    assert any("陈析" in a["actor"] for a in d["audit"] if a["action"] == "decide")
