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
    assert res["valid"] is True
    assert res["support_score"] > 0


def test_filter_drops_rejected_from_score():
    kept, total, rejected = filter_challenger_items(
        [
            {"claim": "ok", "evidence_ids": ["TX-1"], "delta": -0.10},
            {"claim": "bad", "evidence_ids": ["FAKE"], "delta": -0.10},
            {"claim": "huge", "evidence_ids": ["TX-1"], "delta": 0.9},
        ],
        allowed={"TX-1"},
        case_id="A",
    )
    assert len(kept) == 1
    assert len(rejected) == 2
    assert total == -0.10
    assert abs(total) <= DELTA_BOUND
