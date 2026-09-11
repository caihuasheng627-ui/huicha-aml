from app.validator import DELTA_BOUND, filter_challenger_items, validate_claim


def test_delta_over_bound_rejected():
    res = validate_claim(claim="x", evidence_ids=["TX-1"], delta=0.16, allowed={"TX-1"})
    assert res["valid"] is False
    assert "0.15" in res["reason"]


def test_delta_under_bound_rejected():
    res = validate_claim(claim="x", evidence_ids=["TX-1"], delta=-0.151, allowed={"TX-1"})
    assert res["valid"] is False


def test_missing_evidence_rejected():
    res = validate_claim(claim="无证据调分", evidence_ids=[], delta=-0.1, allowed={"TX-1"})
    assert res["valid"] is False
    assert "缺少" in res["reason"]


def test_invalid_evidence_rejected():
    res = validate_claim(claim="x", evidence_ids=["TX-NOPE"], delta=-0.1, allowed={"TX-1"})
    assert res["valid"] is False


def test_fake_evidence_rejected():
    res = validate_claim(claim="x", evidence_ids=["EV-FAKE"], delta=0.05, allowed={"EV-001", "TX-1"})
    assert res["valid"] is False


def test_cross_case_not_in_allowed_is_cross_not_missing():
    res = validate_claim(
        claim="跨案",
        evidence_ids=["TX-A-IN-01"],
        delta=-0.05,
        allowed={"TX-B-01"},
        case_id="ALT-B",
        evidence_case={"TX-A-IN-01": "ALT-A"},
    )
    assert res["valid"] is False
    assert "跨案件" in res["reason"]


def test_cross_case_evidence_rejected():
    res = validate_claim(
        claim="跨案",
        evidence_ids=["EV-001"],
        delta=-0.05,
        allowed={"EV-001"},
        case_id="CASE-A",
        evidence_case={"EV-001": "CASE-B"},
    )
    assert res["valid"] is False
    assert "跨案件" in res["reason"]


def test_valid_claim_passes():
    res = validate_claim(claim="有证", evidence_ids=["TX-1"], delta=-0.1, allowed={"TX-1"}, case_id="A")
    assert res["valid"] is False
    assert "可执行谓词" in res["reason"]


def test_valid_neutral_claim_without_ids_has_zero_membership_score():
    res = validate_claim(claim="中性说明", evidence_ids=[], delta=0, allowed={"TX-1"})
    assert res["valid"] is True
    assert res["support_score"] == 0.0
    assert res["score_kind"] == "id_membership"


def test_filter_drops_rejected_from_score():
    facts = {
        "transactions": [
            {
                "id": "TX-1",
                "from_account": "A",
                "to_account": "B",
                "amount": 10,
                "occurred_at": "2026-09-10 09:00:00",
                "channel": "网银",
            },
            {
                "id": "TX-2",
                "from_account": "B",
                "to_account": "C",
                "amount": 9,
                "occurred_at": "2026-09-10 09:05:00",
                "channel": "网银",
            },
            {
                "id": "TX-3",
                "from_account": "C",
                "to_account": "D",
                "amount": 8,
                "occurred_at": "2026-09-10 09:10:00",
                "channel": "网银",
            },
        ]
    }
    kept, total, rejected = filter_challenger_items(
        [
            {
                "claim": "ok",
                "evidence_ids": ["TX-1", "TX-2", "TX-3"],
                "predicate": "consecutive_transfer_chain",
                "args": {"tx_ids": ["TX-1", "TX-2", "TX-3"]},
                "delta": -0.10,
            },
            {"claim": "bad", "evidence_ids": ["FAKE"], "delta": -0.10},
            {"claim": "huge", "evidence_ids": ["TX-1"], "delta": 0.9},
        ],
        allowed={"TX-1", "TX-2", "TX-3"},
        case_id="A",
        facts=facts,
    )
    assert len(kept) == 1
    assert kept[0]["validation"]["score_kind"] == "predicate_verified"
    assert len(rejected) == 2
    assert total == -0.10
    assert abs(total) <= DELTA_BOUND
