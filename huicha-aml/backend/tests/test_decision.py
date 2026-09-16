from app.decision import normalize_judge, verified_claims_from_judge, verify_judge
from app.llm import build_judge_context
from app.predicates import catalog_for_prompt

FACTS = {
    "transactions": [
        {
            "id": "TX-L-01",
            "from_account": "A",
            "to_account": "B",
            "amount": 3,
            "occurred_at": "2026-09-10 09:01:00",
            "channel": "网银",
        },
        {
            "id": "TX-L-02",
            "from_account": "B",
            "to_account": "C",
            "amount": 2,
            "occurred_at": "2026-09-10 09:07:00",
            "channel": "网银",
        },
        {
            "id": "TX-L-03",
            "from_account": "C",
            "to_account": "D",
            "amount": 1,
            "occurred_at": "2026-09-10 09:16:00",
            "channel": "网银",
        },
    ]
}
ALLOWED = {"TX-L-01", "TX-L-02", "TX-L-03"}
FACTS_SINGLE = {
    "transactions": [
        {
            "id": "TX-X-01",
            "from_account": "6222-X",
            "to_account": "6222-Y",
            "amount": 12000,
            "occurred_at": "2026-09-10 10:00:00",
            "channel": "网银",
        }
    ]
}


def _judge(*, predicate="", args=None, ids=None, text="连续过桥"):
    ids = ids or ["TX-L-01", "TX-L-02", "TX-L-03"]
    row = {"text": text, "evidence_ids": ids}
    if predicate:
        row["predicate"] = predicate
        row["args"] = args or {"tx_ids": ids}
    return {
        "disposition": "suggest_report",
        "confidence": 0.8,
        "typologies": ["layering"],
        "supporting_evidence_ids": ids,
        "contradicting_evidence_ids": [],
        "missing_evidence": [],
        "rationale": [row],
        "next_actions": [],
    }


def test_true_predicate_is_verified_on_rationale():
    decision = normalize_judge(_judge(predicate="consecutive_transfer_chain"))
    result = verify_judge(decision, allowed_evidence=ALLOWED, facts=FACTS)
    assert result["passed"] is True
    claims = verified_claims_from_judge(decision)
    assert claims[0]["predicate"] == "consecutive_transfer_chain"
    assert claims[0]["score_kind"] == "predicate_verified"


def test_false_predicate_is_rebound_when_snapshot_has_true_one():
    decision = normalize_judge(_judge(predicate="amount_monotonic_increasing"))
    result = verify_judge(decision, allowed_evidence=ALLOWED, facts=FACTS)
    assert result["passed"] is True
    claims = verified_claims_from_judge(decision)
    assert claims
    assert claims[0]["predicate"] == "consecutive_transfer_chain"
    assert claims[0]["score_kind"] == "predicate_verified"


def test_cross_case_tx_in_predicate_args_is_sanitized_then_bound():
    decision = normalize_judge(
        _judge(
            predicate="consecutive_transfer_chain",
            args={"tx_ids": ["TX-L-01", "TX-A-IN-01", "TX-L-03"]},
            ids=["TX-L-01"],
        )
    )
    result = verify_judge(decision, allowed_evidence=ALLOWED, facts=FACTS)
    assert result["passed"] is True
    claims = verified_claims_from_judge(decision)
    assert claims
    assert claims[0]["score_kind"] == "predicate_verified"
    assert "TX-A-IN-01" not in (claims[0]["args"].get("tx_ids") or [])


def test_disallowed_predicate_args_are_rebound_from_snapshot():
    decision = normalize_judge(
        _judge(
            predicate="within_time_window_minutes",
            args={"tx_ids": ["TX-L-01", "TX-L-03"], "minutes": 99999},
            ids=["TX-L-01", "TX-L-03"],
        )
    )
    result = verify_judge(decision, allowed_evidence=ALLOWED, facts=FACTS)
    assert result["passed"] is True
    claims = verified_claims_from_judge(decision)
    assert claims
    assert claims[0]["score_kind"] == "predicate_verified"


def test_missing_predicate_on_tx_rationale_is_bound_from_snapshot():
    decision = normalize_judge(_judge())
    result = verify_judge(decision, allowed_evidence=ALLOWED, facts=FACTS)
    assert result["passed"] is True
    claims = verified_claims_from_judge(decision)
    assert claims[0]["predicate"] == "consecutive_transfer_chain"


def test_missing_predicate_on_single_boring_tx_fails():
    decision = normalize_judge(_judge(ids=["TX-X-01"], text="一笔普通转账"))
    result = verify_judge(decision, allowed_evidence={"TX-X-01"}, facts=FACTS_SINGLE)
    assert result["passed"] is False
    assert any(i["kind"] == "missing_predicate" for i in result["issues"])
    assert verified_claims_from_judge(decision) == []


def test_mixed_verified_and_failed_rows_still_pass():
    decision = normalize_judge(
        {
            "disposition": "suggest_report",
            "confidence": 0.8,
            "typologies": ["layering"],
            "supporting_evidence_ids": ["TX-L-01", "TX-L-02", "TX-L-03"],
            "contradicting_evidence_ids": [],
            "missing_evidence": [],
            "rationale": [
                {
                    "text": "连续过桥",
                    "evidence_ids": ["TX-L-01", "TX-L-02", "TX-L-03"],
                    "predicate": "consecutive_transfer_chain",
                    "args": {"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
                },
                {
                    "text": "无法核验的旁路主张",
                    "evidence_ids": ["TX-X-01"],
                    "predicate": "night_transfer",
                    "args": {"tx_ids": ["TX-X-01"]},
                },
            ],
            "next_actions": [],
        }
    )
    result = verify_judge(decision, allowed_evidence=ALLOWED | {"TX-X-01"}, facts={**FACTS, **FACTS_SINGLE, "transactions": FACTS["transactions"] + FACTS_SINGLE["transactions"]})
    assert result["passed"] is True
    assert any(i["kind"] == "predicate_failed" for i in result["issues"])
    assert [i["kind"] for i in result["hard_issues"]] == []
    assert verified_claims_from_judge(decision)[0]["predicate"] == "consecutive_transfer_chain"


def test_tx_plus_kb_without_predicate_is_allowed():
    decision = normalize_judge(_judge(ids=["TX-L-01", "KB-REG-01"], text="结合法规说明资金路径"))
    result = verify_judge(decision, allowed_evidence=ALLOWED | {"KB-REG-01"}, facts=FACTS)
    assert result["passed"] is True


def test_kyc_rationale_without_predicate_is_allowed():
    decision = normalize_judge(_judge(ids=["EV-KYC-01"], text="KYC 等级为关注"))
    result = verify_judge(decision, allowed_evidence={"EV-KYC-01"}, facts=FACTS)
    assert result["passed"] is True
    assert verified_claims_from_judge(decision) == []


def test_build_judge_context_includes_predicate_catalog():
    ctx = build_judge_context(
        alert={"alert_type": "多层", "upstream": "demo"},
        customer={"id": "C-L", "name": "x", "kind": "individual", "industry": "个人", "opened_at": "2026-07-01", "kyc_level": "关注", "summary": ""},
        findings=[],
        transactions=FACTS["transactions"],
        baseline={},
        kb_hits=[],
        allowed_evidence=["TX-L-01"],
    )
    names = {row["name"] for row in ctx["allowed_predicates"]}
    assert names == {row["name"] for row in catalog_for_prompt()}
    assert "consecutive_transfer_chain" in names
