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


def _valid_judge(evidence_id: str, disposition: str = "suggest_report") -> dict:
    return {
        "disposition": disposition,
        "confidence": 0.8,
        "typologies": ["structuring"],
        "supporting_evidence_ids": [evidence_id],
        "contradicting_evidence_ids": [],
        "missing_evidence": ["资金来源说明"],
        "rationale": [{"text": "依据代表性流水", "evidence_ids": [evidence_id]}],
        "next_actions": [],
    }


def _tx_from_kwargs(kwargs, fallback="TX-B-IN-01") -> str:
    allowed = kwargs.get("allowed_evidence") or []
    return next((e for e in allowed if str(e).startswith("TX-")), allowed[0] if allowed else fallback)


def _cf_aware_judge(kwargs, *, missing=None, confidence=0.8):
    prior = kwargs.get("prior_issues") or []
    eid = _tx_from_kwargs(kwargs)
    if any(isinstance(p, dict) and p.get("kind") == "counterfactual" for p in prior):
        decision = _valid_judge(eid, "observe")
        decision["confidence"] = confidence
        return decision, {}
    decision = _valid_judge(eid)
    decision["confidence"] = confidence
    if missing is not None:
        decision["missing_evidence"] = missing
    return decision, {}


def test_truncated_judge_output_gets_one_repair_before_fallback(client, monkeypatch):
    calls: list[list] = []

    def fake_enrich(**kwargs):
        calls.append(kwargs.get("prior_issues") or [])
        if len(calls) == 1:
            raise RuntimeError("Judge 输出超过 max_tokens 被截断（completion_tokens=1000），请压缩证据引用数量")
        return _cf_aware_judge(kwargs)

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-B-20260910/investigate").json()
    assert data["judge_repaired"] is True
    assert data["judge_fallback_reason"] == ""
    assert data["judge_validation"]["passed"] is True
    assert data["judge"]["disposition"] == "suggest_report"
    assert calls[1] and calls[1][0]["kind"] == "invalid_output"
    assert "截断" in calls[1][0]["message"]


def test_judge_missing_evidence_ids_are_sanitized(client, monkeypatch):
    def fake_enrich(**kwargs):
        return _cf_aware_judge(
            kwargs,
            missing=[
                "EV-ALT-B-20260910-001",
                "EV-ALT-B-20260910-002至030",
                "TX-B-IN-02",
                "资金来源说明",
                "受益所有人信息",
            ],
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-B-20260910/investigate").json()
    assert data["judge"]["missing_evidence"] == ["资金来源说明", "受益所有人信息"]
    assert len(data["judge"]["sanitized_missing_evidence"]) == 3
    gaps = [i["title"] for i in data["checklist"]["items"] if i["id"].startswith("AI-GAP-")]
    assert gaps and all("EV-ALT" not in g and "TX-B" not in g for g in gaps)
    assert data["fact_issues"] == []
    assert data["can_sign"] is True


def test_alert_id_in_report_is_not_flagged_by_fact_check(client, monkeypatch):
    from app import agents

    original = agents.enrich_full_report

    def with_alert_id(**kwargs):
        text, usage = original(**kwargs)
        alert_id = kwargs["context"]["alert"]["id"]
        return text + f"\n告警编号 {alert_id}，证据 EV-{alert_id}-001，日期 {alert_id[-8:]}。", usage

    monkeypatch.setattr("app.agents.enrich_full_report", with_alert_id)
    data = client.post("/api/alerts/ALT-L-20260910/investigate").json()
    assert "ALT-L-20260910" in data["report"]["full_text"]
    assert data["fact_issues"] == []
    assert data["can_sign"] is True


def test_counterfactual_invalid_output_is_not_reported_as_unchanged(client, monkeypatch):
    def fake_enrich(**kwargs):
        prior = kwargs.get("prior_issues") or []
        if any(p.get("kind") == "counterfactual" for p in prior):
            return _valid_judge("TX-NOPE-1", disposition="observe"), {}
        return _valid_judge("TX-B-IN-01"), {}

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-B-20260910/investigate").json()
    cf = data["counterfactual"]
    assert cf["performed"] is True
    assert cf["validated"] is False
    assert cf["faithful"] is None
    assert cf["counterfactual_conclusion"] == "observe"
    assert "未通过引用校验" in cf["note"]
    assert "未变化" not in cf["note"]
    assert data["agent_reliability"]["stance"] == "abstain"
    assert data["can_sign"] is False
    assert data["case_v2"]["agent_abstained"] is True


def test_counterfactual_findings_drop_removed_evidence(client, monkeypatch):
    seen: dict = {}

    def fake_enrich(**kwargs):
        prior = kwargs.get("prior_issues") or []
        if any(p.get("kind") == "counterfactual" for p in prior):
            seen["findings"] = kwargs["findings"]
            seen["allowed"] = kwargs["allowed_evidence"]
            return _valid_judge(kwargs["allowed_evidence"][0], disposition="observe"), {}
        return _valid_judge("TX-B-IN-01"), {}

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-B-20260910/investigate").json()
    removed = set(data["counterfactual"]["removed_evidence_ids"])
    assert "TX-B-IN-01" in removed
    assert not (removed & set(seen["allowed"]))
    assert all(not (removed & set(f.get("evidence_ids") or [])) for f in seen["findings"])
    assert data["counterfactual"]["faithful"] is True
    assert data["agent_reliability"]["stance"] == "committed"
    assert data["can_sign"] is True


def test_false_predicate_is_repaired_on_second_round(client, monkeypatch):
    calls: list[list] = []

    def fake_enrich(**kwargs):
        prior = kwargs.get("prior_issues") or []
        calls.append(prior)
        if any(isinstance(p, dict) and p.get("kind") == "counterfactual" for p in prior):
            return _cf_aware_judge(kwargs)
        ids = ["TX-L-01", "TX-L-02", "TX-L-03"]
        if not any(isinstance(p, dict) and p.get("kind") == "predicate_failed" for p in prior):
            return (
                {
                    "disposition": "suggest_report",
                    "confidence": 0.8,
                    "typologies": ["layering"],
                    "supporting_evidence_ids": ids,
                    "contradicting_evidence_ids": [],
                    "missing_evidence": [],
                    "rationale": [
                        {
                            "text": "金额递增",
                            "evidence_ids": ids,
                            "predicate": "amount_monotonic_increasing",
                            "args": {"tx_ids": ids},
                        }
                    ],
                    "next_actions": [],
                },
                {},
            )
        return (
            {
                "disposition": "suggest_report",
                "confidence": 0.8,
                "typologies": ["layering"],
                "supporting_evidence_ids": ids,
                "contradicting_evidence_ids": [],
                "missing_evidence": [],
                "rationale": [
                    {
                        "text": "连续过桥",
                        "evidence_ids": ids,
                        "predicate": "consecutive_transfer_chain",
                        "args": {"tx_ids": ids},
                    }
                ],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-L-20260910/investigate").json()
    assert data["judge_repaired"] is True
    assert data["judge_validation"]["passed"] is True
    assert data["verified_claims"]
    assert data["verified_claims"][0]["predicate"] == "consecutive_transfer_chain"
    assert data["can_sign"] is True
    assert any(any(isinstance(p, dict) and p.get("kind") == "predicate_failed" for p in batch) for batch in calls)


def test_counterfactual_syncs_predicate_args_with_removed_ids(client, monkeypatch):
    seen: dict = {}

    def fake_enrich(**kwargs):
        prior = kwargs.get("prior_issues") or []
        ids = ["TX-L-01", "TX-L-02", "TX-L-03"]
        if any(isinstance(p, dict) and p.get("kind") == "counterfactual" for p in prior):
            allowed = [e for e in (kwargs.get("allowed_evidence") or []) if str(e).startswith("TX-")]
            seen["allowed"] = allowed
            kept = [e for e in ids if e in allowed]
            return (
                {
                    "disposition": "observe",
                    "confidence": 0.6,
                    "typologies": [],
                    "supporting_evidence_ids": kept[:1],
                    "contradicting_evidence_ids": [],
                    "missing_evidence": ["资金来源说明"],
                    "rationale": [{"text": "移除过桥后仅余观察", "evidence_ids": kept[:1] or allowed[:1]}],
                    "next_actions": [],
                },
                {},
            )
        return (
            {
                "disposition": "suggest_report",
                "confidence": 0.8,
                "typologies": ["layering"],
                "supporting_evidence_ids": ids,
                "contradicting_evidence_ids": [],
                "missing_evidence": [],
                "rationale": [
                    {
                        "text": "连续过桥",
                        "evidence_ids": ids,
                        "predicate": "consecutive_transfer_chain",
                        "args": {"tx_ids": ids},
                    }
                ],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-L-20260910/investigate").json()
    removed = set(data["counterfactual"]["removed_evidence_ids"])
    assert removed
    assert not (removed & set(seen["allowed"]))
    assert data["counterfactual"]["validated"] is True
    assert data["verified_claims"][0]["args"]["tx_ids"] == ["TX-L-01", "TX-L-02", "TX-L-03"]


def test_low_confidence_rule_conflict_abstains(client, monkeypatch):
    def fake_enrich(**kwargs):
        decision, usage = _cf_aware_judge(kwargs, confidence=0.4)
        if not any(isinstance(p, dict) and p.get("kind") == "counterfactual" for p in (kwargs.get("prior_issues") or [])):
            decision["disposition"] = "suggest_report"
            decision["confidence"] = 0.4
        return decision, usage

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    data = client.post("/api/alerts/ALT-A-20260910/investigate").json()
    assert data["rule_baseline"]["conclusion"] != data["judge"]["disposition"] or data["judge"]["confidence"] < 0.55
    assert data["agent_reliability"]["stance"] == "abstain"
    assert any(r["code"] == "rule_judge_conflict_low_conf" for r in data["agent_reliability"]["reasons"])
    assert data["can_sign"] is False
    assert "倾向档" in data["report"]["full_text"]


def test_stable_high_confidence_layering_remains_signable(client):
    data = client.post("/api/alerts/ALT-L-20260910/investigate").json()
    assert data["rule_baseline"]["conclusion"] == "exclude"
    assert data["judge"]["disposition"] == "suggest_report"
    assert data["judge"]["confidence"] >= 0.55
    assert data["judge_validation"]["passed"] is True
    assert data["agent_reliability"]["stance"] == "committed"
    assert data["case_v2"]["agent_abstained"] is False
    assert data["can_sign"] is True
    assert data["prompt_versions"]["judge"] == "judge_v3p"
    assert data["evidence_sufficiency"]["method"] == "bounded_greedy"

