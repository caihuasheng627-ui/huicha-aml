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


def test_false_predicate_with_real_ids_rejected_in_pipeline(client, monkeypatch):
    def fake_enrich(**_kwargs):
        return (
            [
                {
                    "claim": "金额递增（假）",
                    "detail": "引用真编号但陈述为假",
                    "evidence_ids": ["TX-L-01", "TX-L-02", "TX-L-03"],
                    "predicate": "amount_monotonic_increasing",
                    "args": {"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
                    "delta": -0.10,
                }
            ],
            {},
        )

    monkeypatch.setattr("app.agents.enrich_challenger", fake_enrich)
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    reasons = " ".join((x.get("validation") or {}).get("reason") or "" for x in data["rejected_claims"])
    assert "不成立" in reasons
    assert data["scoring"]["llm_delta"] == 0.0


def test_pipeline_records_rejected(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    data = r.json()
    assert "rejected_claims" in data
    assert abs(data["scoring"]["llm_delta"]) <= 0.15
    roles = [s["role"] for s in data["steps"]]
    assert "Challenger" in roles
    assert "Validator" in roles
    assert any(e["evidence_id"].startswith("EV-ALT-A-20260910-") for e in data["evidence_graph"])


def test_cross_case_tx_rejected_in_pipeline(client, monkeypatch):
    a = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    assert a.status_code == 200

    def fake_enrich(**_kwargs):
        return (
            [{"claim": "跨案引用", "detail": "不应进分", "evidence_ids": ["TX-A-IN-01"], "delta": -0.10}],
            {},
        )

    monkeypatch.setattr("app.agents.enrich_challenger", fake_enrich)
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    reasons = " ".join((x.get("validation") or {}).get("reason") or "" for x in data["rejected_claims"])
    assert "跨案件" in reasons
    assert data["scoring"]["llm_delta"] == 0.0


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


def test_challenger_run_payload_on(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["case_challenger_enabled"] is True
    assert data["use_challenger"] is True
    run = data["challenger_run"]
    assert run["enabled"] is True
    assert run["ablation"] is False
    assert abs(run["llm_delta"]) <= 0.15
    assert abs(data["scoring"]["llm_delta"]) <= 0.15
    assert run["delta_bound"] == 0.15
    assert run["initial_label"]
    assert run["final_label"]
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


def test_invalid_challenger_evidence_zeroes_delta(client, monkeypatch):
    def fake_enrich(**_kwargs):
        return (
            [{"claim": "不存在的流水", "detail": "应被拒绝", "evidence_ids": ["TX-NOPE-99"], "delta": -0.10}],
            {},
        )

    monkeypatch.setattr("app.agents.enrich_challenger", fake_enrich)
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scoring"]["llm_delta"] == 0.0
    assert data["validator_result"]["passed"] is False
    assert "未通过证据校验" in data["validator_result"]["reason"]
    assert data["rejected_claims"]
    actions = [a["action"] for a in client.get("/api/alerts/ALT-B-20260910").json()["audit"]]
    assert "validator" in actions


def test_exclude_case_does_not_stack_negative_llm(client, monkeypatch):
    ids = ["TX-E-01", "TX-E-02", "TX-E-03", "TX-E-04", "TX-E-05"]

    def fake_enrich(**_kwargs):
        return (
            [
                {
                    "claim": "金额按时间递增",
                    "detail": "经营收款自然增长",
                    "evidence_ids": ids,
                    "predicate": "amount_monotonic_increasing",
                    "args": {"tx_ids": ids},
                    "delta": -0.15,
                },
                {
                    "claim": "均在夜间",
                    "detail": "符合夜结",
                    "evidence_ids": ids[:4],
                    "predicate": "night_transfer",
                    "args": {"tx_ids": ids[:4]},
                    "delta": -0.10,
                },
                {
                    "claim": "POS 前缀",
                    "detail": "收银通道",
                    "evidence_ids": ids,
                    "predicate": "counterparty_has_prefix",
                    "args": {"tx_ids": ids, "prefix": "POS-", "side": "from"},
                    "delta": -0.10,
                },
            ],
            {},
        )

    monkeypatch.setattr("app.agents.enrich_challenger", fake_enrich)
    r = client.post("/api/alerts/ALT-E-20260908/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    scoring = data["scoring"]
    run = data["challenger_run"]
    assert run["initial_label"] == "排除"
    assert run["raw_delta"] == -0.35
    assert run["clamped_delta"] == -0.15
    assert run["delta_clamped"] is True
    assert run["delta_suppressed"] is True
    assert scoring["llm_delta"] == 0.0
    expected_raw = round(scoring["base"] + scoring["rule_prior"], 4)
    assert scoring["raw"] == expected_raw
    assert scoring["final"] == max(0.05, min(0.95, expected_raw))
    assert scoring["delta_suppressed"] is True
    assert data["conclusion"] == "exclude"


def test_report_case_still_applies_negative_llm(client, monkeypatch):
    ids = ["TX-B-IN-01", "TX-B-IN-02", "TX-B-IN-03"]

    def fake_enrich(**_kwargs):
        return (
            [
                {
                    "claim": "现金存入带 CASH 前缀",
                    "detail": "对手类型可核验",
                    "evidence_ids": ids,
                    "predicate": "counterparty_has_prefix",
                    "args": {"tx_ids": ids, "prefix": "CASH-", "side": "from"},
                    "delta": -0.10,
                }
            ],
            {},
        )

    monkeypatch.setattr("app.agents.enrich_challenger", fake_enrich)
    r = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    run = data["challenger_run"]
    assert run["initial_label"] == "建议上报"
    assert run["delta_suppressed"] is False
    assert data["scoring"]["llm_delta"] == -0.10
    assert data["scoring"]["raw"] == round(
        data["scoring"]["base"] + data["scoring"]["rule_prior"] - 0.10, 4
    )
