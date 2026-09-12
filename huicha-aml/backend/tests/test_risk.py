from app.risk import aggregate, clamp01, counterfactual, score_to_conclusion, score_to_level


def test_aggregate_clamps_and_records_source():
    risk = aggregate(
        [
            {"code": "base-risk", "label": "底", "delta": 0.12, "evidence_ids": [], "source": "rule"},
            {"code": "vel", "label": "速度", "delta": 0.40, "evidence_ids": ["TX-1"], "source": "rule"},
            {"code": "counter", "label": "反证", "delta": -0.05, "evidence_ids": ["TX-2"], "source": "rule"},
        ],
        challenger_delta=-0.10,
    )
    assert 0 <= risk["final"] <= 1
    assert risk["final"] == 0.37
    assert risk["recommendation"] in {"CLOSE", "MONITOR", "EDD", "REPORT_REVIEW"}
    assert all("source" in f for f in risk["factors"])
    assert risk["conclusion"] == "observe"


def test_llm_cannot_set_final_directly():
    risk = aggregate([{"code": "x", "label": "x", "delta": 9.9, "source": "rule"}])
    assert risk["final"] <= 0.95
    assert clamp01(3) == 1.0


def test_counterfactual_rule_rerun():
    factors = [
        {"code": "base-risk", "label": "底", "delta": 0.12},
        {"code": "vel", "label": "速度", "delta": 0.40},
    ]
    cf = counterfactual(factors, ["vel"])
    assert cf["original"] > cf["counterfactual"]
    assert cf["dropped"] == ["vel"]
    assert "synthetic" in cf["data_note"]
    assert "若无此疑点" in cf["assumption"]
    assert "速度" in cf["assumption"]
    assert cf["alt_label"]


def test_counterfactual_caps_two_and_can_drop_challenger():
    factors = [
        {"code": "a", "label": "拆分", "delta": 0.30},
        {"code": "b", "label": "夜间", "delta": 0.20},
        {"code": "c", "label": "名单", "delta": 0.10},
    ]
    cf = counterfactual(factors, ["a", "b", "c"], challenger_delta=-0.12, drop_challenger=True)
    assert cf["dropped"] == ["a"]
    assert cf["drop_challenger"] is True
    assert "Challenger" in cf["assumption"]
    both = counterfactual(factors, ["a", "b"], challenger_delta=-0.12, drop_challenger=False)
    assert both["dropped"] == ["a", "b"]
    assert both["drop_challenger"] is False


def test_score_bands():
    assert score_to_conclusion(0.2) == "exclude"
    assert score_to_conclusion(0.4) == "observe"
    assert score_to_conclusion(0.7) == "suggest_report"
    assert score_to_level(0.2) == "LOW"
    assert score_to_level(0.4) == "MEDIUM"
    assert score_to_level(0.7) == "HIGH"
