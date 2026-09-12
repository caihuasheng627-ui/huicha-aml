import json

from app.validator import filter_challenger_items


def test_challenger_cannot_change_final_without_validation():
    kept, total, rejected = filter_challenger_items(
        [{"claim": "夸大", "evidence_ids": ["TX-1"], "delta": 0.99}],
        allowed={"TX-1"},
    )
    assert kept == []
    assert rejected
    assert total == 0.0


def test_bounded_delta_accepted():
    facts = {
        "transactions": [
            {
                "id": "TX-1",
                "from_account": "A",
                "to_account": "RELATIVE-01",
                "amount": 300000,
                "occurred_at": "2026-08-20 10:00:00",
                "channel": "柜面",
            }
        ]
    }
    kept, total, _ = filter_challenger_items(
        [
            {
                "claim": "经营解释",
                "evidence_ids": ["TX-1"],
                "predicate": "counterparty_has_prefix",
                "args": {"tx_ids": ["TX-1"], "prefix": "RELATIVE-", "side": "to"},
                "delta": -0.10,
            }
        ],
        allowed={"TX-1"},
        facts=facts,
    )
    assert kept[0]["delta"] == -0.10
    assert kept[0]["validation"]["score_kind"] == "predicate_verified"
    assert total == -0.10


def test_uncited_judge_rationale_rejected_in_pipeline(client, monkeypatch):
    def fake_enrich(**_kwargs):
        return (
            {
                "disposition": "suggest_report",
                "confidence": 0.8,
                "typologies": ["layering"],
                "supporting_evidence_ids": ["TX-L-01"],
                "contradicting_evidence_ids": [],
                "missing_evidence": [],
                "rationale": [{"text": "没有引用的理由", "evidence_ids": []}],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["judge_validation"]["passed"] is False
    assert any(x["kind"] == "uncited_rationale" for x in data["rejected_claims"])
    assert data["can_sign"] is False


def test_pipeline_records_rejected(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    data = r.json()
    assert "rejected_claims" in data
    assert data["scoring"]["mode"] == "judge_not_additive"
    roles = [s["role"] for s in data["steps"]]
    assert "Judge" in roles
    assert "Skeptic" in roles
    assert any(e["evidence_id"].startswith("EV-ALT-A-20260910-J") for e in data["evidence_graph"])


def test_cross_case_tx_rejected_in_pipeline(client, monkeypatch):
    a = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    assert a.status_code == 200

    def fake_enrich(**_kwargs):
        return (
            {
                "disposition": "exclude",
                "confidence": 0.7,
                "typologies": [],
                "supporting_evidence_ids": ["TX-A-IN-01"],
                "contradicting_evidence_ids": [],
                "missing_evidence": [],
                "rationale": [{"text": "跨案引用", "evidence_ids": ["TX-A-IN-01"]}],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["judge_validation"]["passed"] is False
    assert "TX-A-IN-01" in data["judge_validation"]["invalid_ids"]


def test_two_cases_persist_distinct_evidence_pk(client):
    from app.database import SessionLocal
    from app.models import Evidence

    a = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    b = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert a.status_code == 200 and b.status_code == 200
    ids_a = {e["evidence_id"] for e in a.json()["evidence_graph"]}
    ids_b = {e["evidence_id"] for e in b.json()["evidence_graph"]}
    assert ids_a and ids_b
    assert ids_a.isdisjoint(ids_b)
    db = SessionLocal()
    try:
        rows = db.query(Evidence).all()
        cases = {e.case_id for e in rows}
        assert "ALT-A-20260910" in cases
        assert "ALT-B-20260910" in cases
    finally:
        db.close()


def test_seed_tx_mapped_to_own_alert(client):
    from app.case_store import evidence_case_index
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        idx = evidence_case_index(db)
        assert idx["TX-A-IN-01"] == "ALT-A-20260910"
        assert idx["TX-B-IN-01"] == "ALT-B-20260910"
        assert "KB-REG-01" not in idx
    finally:
        db.close()


def test_judge_run_payload_on(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["case_challenger_enabled"] is True
    assert data["use_challenger"] is True
    run = data["challenger_run"]
    assert run["enabled"] is True
    assert run["ablation"] is False
    assert run["initial_label"]
    assert run["final_label"]
    assert data["scoring"]["llm_delta"] == 0.0
    assert data["scoring"]["mode"] == "judge_not_additive"
    assert data["judge"]["rationale"]
    assert data["validator_result"]["passed"] is True


def test_case_history_keeps_challenger_off(client):
    off = client.post(
        "/api/alerts/ALT-C-20260910/investigate",
        params={"use_challenger": False, "experiment_mode": True},
    )
    assert off.status_code == 200, off.text
    payload = off.json()
    assert payload["case_challenger_enabled"] is False
    assert payload["use_challenger"] is False
    assert payload["challenger_run"]["ablation"] is True
    assert payload["experiment_mode"] is True
    stored_score = payload["scoring"]["final"]
    stored_conc = payload["conclusion"]

    loaded = client.get("/api/alerts/ALT-C-20260910").json()["investigation"]
    assert loaded["case_challenger_enabled"] is False
    assert loaded["scoring"]["final"] == stored_score
    assert loaded["conclusion"] == stored_conc

    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    still = client.get("/api/alerts/ALT-C-20260910").json()["investigation"]
    assert still["case_challenger_enabled"] is False
    assert still["conclusion"] == stored_conc
    assert still["scoring"]["final"] == stored_score

    rerun = client.post(
        "/api/alerts/ALT-C-20260910/investigate",
        params={"use_challenger": True, "experiment_mode": True},
    )
    assert rerun.status_code == 200, rerun.text
    updated = rerun.json()
    assert updated["case_challenger_enabled"] is True
    assert updated["challenger_run"]["ablation"] is False


def test_audit_records_challenger_flags(client):
    r = client.post(
        "/api/alerts/ALT-C-20260910/investigate",
        params={"use_challenger": False, "experiment_mode": True},
    )
    assert r.status_code == 200, r.text
    d = client.get("/api/alerts/ALT-C-20260910").json()
    inv_row = [a for a in d["audit"] if a["action"] == "investigate"][-1]
    detail = json.loads(inv_row["detail"])
    assert detail["case_id"] == "ALT-C-20260910"
    assert detail["challenger_enabled"] is False
    assert detail["experiment_mode"] is True
    assert detail["challenger_off_reason"] == "实验模式消融"
    assert "rule_prior" in detail
    assert "llm_delta" in detail
    assert "final_score" in detail
    assert "validator_result" in detail
    assert "evidence_ids" in detail
    assert "counter_evidence_ids" in detail
    assert "prompt_versions" in detail
    assert detail["judge_decision"]
    assert detail["rule_baseline"]


def test_invalid_judge_evidence_blocks_signing(client, monkeypatch):
    def fake_enrich(**_kwargs):
        return (
            {
                "disposition": "suggest_report",
                "confidence": 0.9,
                "typologies": ["structuring"],
                "supporting_evidence_ids": ["TX-NOPE-99"],
                "contradicting_evidence_ids": [],
                "missing_evidence": [],
                "rationale": [{"text": "引用不存在流水", "evidence_ids": ["TX-NOPE-99"]}],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["validator_result"]["passed"] is False
    assert "证据契约" in data["validator_result"]["reason"]
    assert data["rejected_claims"]
    assert data["can_sign"] is False
    actions = [a["action"] for a in client.get("/api/alerts/ALT-B-20260910").json()["audit"]]
    assert "validator" in actions


def test_rule_baseline_and_judge_are_not_added(client):
    r = client.post("/api/alerts/ALT-C-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["rule_baseline"]["conclusion"] == "observe"
    assert data["judge"]["disposition"] == "suggest_report"
    assert data["conclusion"] == "suggest_report"
    assert data["scoring"]["mode"] == "judge_not_additive"
    assert data["scoring"]["llm_delta"] == 0.0


def test_upstream_alert_label_does_not_directly_raise_rule_baseline(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": False})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["alert"]["alert_type"]
    assert data["rule_baseline"]["score"] == 0.12
    assert all(f["code"] != "upstream-alert" for f in data["rule_baseline"]["factors"])


def test_watchlist_guardrail_prevents_direct_exclusion(client, monkeypatch):
    def fake_enrich(**kwargs):
        evidence_id = kwargs["allowed_evidence"][0]
        return (
            {
                "disposition": "exclude",
                "confidence": 0.8,
                "typologies": [],
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [evidence_id],
                "missing_evidence": [],
                "rationale": [{"text": "建议排除", "evidence_ids": [evidence_id]}],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-C-20260910/investigate").json()
    assert data["watch_hits"]
    assert data["judge"]["disposition"] == "exclude"
    assert data["conclusion"] == "observe"
    assert data["policy_guardrails"]["overridden"] is True


def test_judge_missing_evidence_flows_into_checklist(client, monkeypatch):
    original = __import__("app.agents", fromlist=["enrich_judge"]).enrich_judge

    def with_gap(**kwargs):
        decision, usage = original(**kwargs)
        decision["missing_evidence"] = ["补充实际控制人关系证明"]
        return decision, usage

    monkeypatch.setattr("app.agents.enrich_judge", with_gap)
    data = client.post("/api/alerts/ALT-A-20260910/investigate").json()
    gaps = [i for i in data["checklist"]["items"] if i["id"].startswith("AI-GAP-")]
    assert gaps
    assert gaps[0]["status"] == "missing"


def test_reporter_generates_all_four_sections(client):
    data = client.post("/api/alerts/ALT-B-20260910/investigate").json()
    text = data["report"]["full_text"]
    for section in ("资金交易及客户行为", "疑点分析", "反证与缺失证据", "结论与理由"):
        assert f"【{section}】" in text
