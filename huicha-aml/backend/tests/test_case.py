from app.evidence import build_evidence_graph


def test_relationship_click_source_is_tx():
    bundle = {
        "alert": {"id": "ALT-X", "account_id": "6222-L-B", "created_at": "2026-09-10"},
        "customer": {
            "id": "C-L",
            "name": "x",
            "industry": "个人",
            "opened_at": "2026-07-01",
            "kind": "individual",
            "kyc_level": "普通",
        },
        "transactions": [],
        "graph": {
            "edges": [
                {
                    "source": "6222-L-A",
                    "target": "6222-L-B",
                    "amount": 98000,
                    "count": 1,
                    "tx_ids": ["TX-L-01"],
                }
            ]
        },
    }
    rel = [e for e in build_evidence_graph("ALT-X", bundle, []) if e["evidence_type"] == "RELATIONSHIP"]
    assert rel[0]["source_id"] == "TX-L-01"
    assert rel[0]["raw_reference"] == "TX-L-01"


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
    assert data["prompt_versions"]["challenger"] == "challenger_v3"
    assert data["prompt_versions"]["validator"] == "validator_v2"


def test_layering_demo_chain(client):
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    tx_ids = {t["id"] for t in data["transactions"]}
    assert {"TX-L-01", "TX-L-02", "TX-L-03"} <= tx_ids
    assert data["conclusion"] == "suggest_report"
    verified = [c for c in data["challenger"] if (c.get("validation") or {}).get("score_kind") == "predicate_verified"]
    assert verified
    assert verified[0]["predicate"]
    assert data["case_v2"]["recommendation"] == "REPORT_REVIEW"
    assert "layering" in data["case_v2"]["suspicious_types"]
    rel = [e for e in data["evidence_graph"] if e["evidence_type"] == "RELATIONSHIP"]
    assert rel
    assert all(
        (e.get("source_id") or "").startswith("TX-") or not e.get("raw_reference") for e in rel if e.get("raw_reference")
    )


def test_agent_cannot_auto_report(client, auth_headers):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    d = client.post(
        "/api/alerts/ALT-B-20260910/decide",
        json={"decision": "confirm", "note": ""},
        headers=auth_headers,
    )
    assert d.status_code == 200
    body = d.json()
    assert body["final_action"] == "human_only"
    assert "自动报送" in body["note"]
    assert body["signed_by_name"] == "陈析"


def test_observe_confirm_is_monitoring_not_filing(client, auth_headers):
    client.post("/api/alerts/ALT-F-20260910/investigate", params={"use_challenger": True})
    d = client.post(
        "/api/alerts/ALT-F-20260910/decide",
        json={"decision": "confirm", "note": ""},
        headers=auth_headers,
    )
    assert d.status_code == 200
    assert d.json()["status"] == "monitoring"
    detail = client.get("/api/alerts/ALT-F-20260910").json()
    assert detail["alert"]["status"] == "monitoring"
    assert (detail["investigation"] or {}).get("case_v2", {}).get("status") == "CLOSED"
    assert (detail["investigation"] or {}).get("case_v2", {}).get("human_decision") == "confirm"
