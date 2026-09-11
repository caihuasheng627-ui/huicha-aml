from app.predicates import execute_predicate, pick_true_predicate, stub_challenger_item
from app.validator import filter_challenger_items, validate_claim

LAYERING = {
    "transactions": [
        {
            "id": "TX-L-01",
            "from_account": "6222-L-A",
            "to_account": "6222-L-B",
            "amount": 98000.0,
            "occurred_at": "2026-09-10 09:01:00",
            "channel": "网银",
        },
        {
            "id": "TX-L-02",
            "from_account": "6222-L-B",
            "to_account": "6222-L-C",
            "amount": 97500.0,
            "occurred_at": "2026-09-10 09:07:00",
            "channel": "网银",
        },
        {
            "id": "TX-L-03",
            "from_account": "6222-L-C",
            "to_account": "6222-L-D",
            "amount": 96800.0,
            "occurred_at": "2026-09-10 09:16:00",
            "channel": "网银",
        },
    ]
}
ALLOWED = {"TX-L-01", "TX-L-02", "TX-L-03"}


def test_chain_and_decreasing_true():
    chain = execute_predicate(
        "consecutive_transfer_chain",
        {"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
        LAYERING,
    )
    dec = execute_predicate(
        "amount_monotonic_decreasing",
        {"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
        LAYERING,
    )
    inc = execute_predicate(
        "amount_monotonic_increasing",
        {"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
        LAYERING,
    )
    assert chain["ok"] and chain["true"]
    assert dec["ok"] and dec["true"]
    assert inc["ok"] and not inc["true"]


def test_unknown_predicate_not_ok():
    res = execute_predicate("not_a_real_predicate", {"tx_ids": ["TX-L-01"]}, LAYERING)
    assert res["ok"] is False
    assert "未知谓词" in res["reason"]


def test_minutes_out_of_bound_rejected():
    res = execute_predicate(
        "within_time_window_minutes",
        {"tx_ids": ["TX-L-01", "TX-L-03"], "minutes": 99999},
        LAYERING,
    )
    assert res["ok"] is False
    assert "允许集合" in res["reason"]


def test_true_predicate_claim_enters_score():
    res = validate_claim(
        claim="短时过桥",
        evidence_ids=["TX-L-01", "TX-L-02", "TX-L-03"],
        delta=-0.10,
        allowed=ALLOWED,
        predicate="consecutive_transfer_chain",
        args={"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
        facts=LAYERING,
    )
    assert res["valid"] is True
    assert res["score_kind"] == "predicate_verified"


def test_false_predicate_with_real_ids_rejected():
    res = validate_claim(
        claim="金额递增（假）",
        evidence_ids=["TX-L-01", "TX-L-02", "TX-L-03"],
        delta=-0.10,
        allowed=ALLOWED,
        predicate="amount_monotonic_increasing",
        args={"tx_ids": ["TX-L-01", "TX-L-02", "TX-L-03"]},
        facts=LAYERING,
    )
    assert res["valid"] is False
    assert res["score_kind"] == "predicate_failed"
    assert "不成立" in res["reason"]


def test_scoring_delta_without_predicate_rejected():
    res = validate_claim(claim="无谓词调分", evidence_ids=["TX-L-01"], delta=-0.10, allowed=ALLOWED, facts=LAYERING)
    assert res["valid"] is False
    assert "可执行谓词" in res["reason"]


def test_pick_true_predicate_for_layering():
    picked = pick_true_predicate(LAYERING, ALLOWED)
    assert picked
    assert picked["predicate"] == "consecutive_transfer_chain"


def test_stub_item_is_verifiable():
    item = stub_challenger_item(
        {"transactions": LAYERING["transactions"], "allowed_evidence_ids": list(ALLOWED)},
        claim="stub",
        detail="d",
        delta=-0.12,
    )
    kept, total, rejected = filter_challenger_items([item], allowed=ALLOWED, facts=LAYERING)
    assert not rejected
    assert kept[0]["validation"]["score_kind"] == "predicate_verified"
    assert total == -0.12
