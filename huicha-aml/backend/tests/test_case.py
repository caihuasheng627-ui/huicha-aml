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
    assert data["prompt_versions"]["judge"] == "judge_v3"
    assert data["judge_validation"]["passed"] is True
    assert data["scoring"]["mode"] == "judge_not_additive"
    assert data["prompt_versions"]["skeptic"] == "skeptic_v1"


def test_layering_demo_chain(client):
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    tx_ids = {t["id"] for t in data["transactions"]}
    assert {"TX-L-01", "TX-L-02", "TX-L-03"} <= tx_ids
    assert data["conclusion"] == "suggest_report"
    assert data["judge"]["supporting_evidence_ids"]
    assert data["rule_baseline"]["conclusion"] == "exclude"
    assert data["judge"]["disposition"] == "suggest_report"
    assert data["case_v2"]["recommendation"] == "REPORT_REVIEW"
    assert "layering" in data["case_v2"]["suspicious_types"]
    rel = [e for e in data["evidence_graph"] if e["evidence_type"] == "RELATIONSHIP"]
    assert rel
    assert all(
        (e.get("source_id") or "").startswith("TX-") or not e.get("raw_reference") for e in rel if e.get("raw_reference")
    )


from tests.conftest import dual_confirm


def test_agent_cannot_auto_report(client, auth_headers):
    client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    d, _ = dual_confirm(client, "ALT-B-20260910")
    assert d.status_code == 200
    body = d.json()
    assert body["final_action"] == "human_only"
    assert "自动报送" in body["note"]
    assert body["signed_by_name"] == "李审"


def test_observe_confirm_is_monitoring_not_filing(client, auth_headers):
    client.post("/api/alerts/ALT-F-20260910/investigate", params={"use_challenger": True})
    d, _ = dual_confirm(client, "ALT-F-20260910")
    assert d.status_code == 200
    assert d.json()["status"] == "monitoring"
    detail = client.get("/api/alerts/ALT-F-20260910").json()
    assert detail["alert"]["status"] == "monitoring"
    assert (detail["investigation"] or {}).get("case_v2", {}).get("status") == "CLOSED"
    assert (detail["investigation"] or {}).get("case_v2", {}).get("human_decision") == "confirm"


def test_case_h_sampling_keeps_cash_and_caps_judge_context(client, monkeypatch):
    import json

    import app.llm as llm_mod

    captured = {}
    orig = llm_mod.chat

    def wrap(messages, *, temperature=0.0, max_tokens=900):
        sys = messages[0]["content"]
        user = messages[-1]["content"]
        if ("调查 Judge" in sys or "disposition" in sys) and "ctx" not in captured:
            captured["len"] = len(user)
            captured["ctx"] = json.loads(user)
        return orig(messages, temperature=temperature, max_tokens=max_tokens)

    monkeypatch.setattr(llm_mod, "chat", wrap)
    r = client.post("/api/alerts/ALT-H-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    sampling = data["sampling"]
    assert sampling["summary"]["total"] >= 150
    assert sampling["summary"]["sampled"] <= 30
    sample_ids = {t["id"] for t in sampling["sample"]}
    assert any(i.startswith("TX-H-CASH") for i in sample_ids)
    assert "TX-H-NIGHT-01" in sample_ids
    assert len(data["timeline"]) >= 150
    assert len(data["transactions"]) >= 150
    assert captured["ctx"]["transactions"]
    assert len(captured["ctx"]["transactions"]) <= 30
    assert captured["len"] < 25000
    assert any(t["id"].startswith("TX-H-CASH") for t in captured["ctx"]["transactions"])
    assert captured["ctx"]["transaction_summary"]["total"] >= 150
    cluster_count = sum(c["count"] for c in captured["ctx"]["transaction_clusters"])
    assert cluster_count == sampling["summary"]["total"]
    cluster_ids = {i for c in sampling["clusters"] for i in (c.get("representative_ids") or [])}
    citable = sample_ids | cluster_ids
    cited = set(data["judge"].get("supporting_evidence_ids") or []) | set(
        data["judge"].get("contradicting_evidence_ids") or []
    )
    for row in data["judge"].get("rationale") or []:
        cited.update(row.get("evidence_ids") or [])
    tx_cited = {x for x in cited if str(x).startswith("TX-")}
    assert tx_cited <= citable
    assert data["judge_validation"]["passed"] is True
    assert not data["judge_validation"].get("invalid_ids")
    prompt_allowed = set(captured["ctx"].get("allowed_evidence_ids") or [])
    assert tx_cited <= prompt_allowed
    for finding in captured["ctx"].get("findings") or []:
        for eid in finding.get("evidence_ids") or []:
            if str(eid).startswith("TX-"):
                assert eid in citable
    assert data["can_sign"] is True
    assert "窗口内共" in (data["report"].get("behavior") or data["report"].get("full_text") or "")


def test_case_h_rejects_citation_outside_sample(client, monkeypatch):
    def fake_enrich(**_kwargs):
        return (
            {
                "disposition": "suggest_report",
                "confidence": 0.7,
                "typologies": ["structuring"],
                "supporting_evidence_ids": ["TX-H-CASH-01"],
                "contradicting_evidence_ids": ["TX-H-POS-050"],
                "missing_evidence": [],
                "rationale": [
                    {"text": "贴线现金", "evidence_ids": ["TX-H-CASH-01"]},
                    {"text": "日常 POS", "evidence_ids": ["TX-H-POS-050"]},
                ],
                "next_actions": ["人工复核"],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    r = client.post("/api/alerts/ALT-H-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    sample_ids = {t["id"] for t in data["sampling"]["sample"]}
    cluster_ids = {i for c in data["sampling"]["clusters"] for i in (c.get("representative_ids") or [])}
    assert "TX-H-POS-050" not in sample_ids | cluster_ids
    assert data["judge_validation"]["passed"] is False
    assert "TX-H-POS-050" in data["judge_validation"]["invalid_ids"]
