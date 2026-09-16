from app.reliability import LOW_CONFIDENCE, compute_reliability


def test_hard_citation_and_fallback_abstain():
    citation = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.9},
        judge_validation={"passed": False, "issues": [{"kind": "invalid_citation"}]},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": False},
        evidence_sufficiency={"verified": True, "necessary_ids": ["TX-1"]},
    )
    assert citation["stance"] == "abstain"
    assert any(r["code"] == "citation_failed" and r["severity"] == "hard" for r in citation["reasons"])

    fallback = compute_reliability(
        use_challenger=True,
        judge={"disposition": "exclude", "confidence": 0.2},
        judge_validation={"passed": False, "score_kind": "fallback", "issues": [{"kind": "judge_failure"}]},
        fallback_reason="timeout",
        baseline={"conclusion": "exclude"},
        counterfactual={"performed": False},
        evidence_sufficiency={"verified": True, "necessary_ids": []},
    )
    assert any(r["code"] == "judge_fallback" for r in fallback["reasons"])

    pred = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.8},
        judge_validation={"passed": False, "issues": [{"kind": "predicate_failed"}]},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": False},
        evidence_sufficiency={"verified": True, "necessary_ids": []},
    )
    assert any(r["code"] == "predicate_failed" for r in pred["reasons"])

    missing = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.8},
        judge_validation={"passed": False, "issues": [{"kind": "missing_predicate"}]},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": False},
        evidence_sufficiency={"verified": True, "necessary_ids": []},
    )
    assert any(r["code"] == "missing_predicate" and r["severity"] == "hard" for r in missing["reasons"])
    assert not any(r["code"] == "citation_failed" for r in missing["reasons"])


def test_cf_invalid_is_hard_without_greedy_core():
    result = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.8},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": True, "validated": False, "faithful": None},
        evidence_sufficiency={"verified": False, "necessary_ids": []},
    )
    assert result["stance"] == "abstain"
    assert any(r["code"] == "cf_invalid" and r["severity"] == "hard" for r in result["reasons"])


def test_cf_invalid_does_not_override_greedy_core():
    result = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.8},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": True, "validated": False, "faithful": None},
        evidence_sufficiency={"verified": True, "necessary_ids": ["TX-1"]},
    )
    assert result["stance"] == "committed"
    assert not any(r["code"] == "cf_invalid" for r in result["reasons"])


def test_soft_low_conf_conflict_and_stable_high_conf_committed():
    low = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": LOW_CONFIDENCE - 0.01},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "exclude"},
        counterfactual={"performed": True, "validated": True},
        evidence_sufficiency={"verified": True, "necessary_ids": ["TX-L-01"]},
    )
    assert low["stance"] == "abstain"
    assert any(r["code"] == "rule_judge_conflict_low_conf" for r in low["reasons"])

    high = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.78},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "exclude"},
        counterfactual={"performed": True, "validated": True, "faithful": True},
        evidence_sufficiency={"verified": True, "necessary_ids": ["TX-L-01"]},
    )
    assert high["stance"] == "committed"


def test_cf_not_dependent_only_for_report_without_necessary_core():
    report = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.8},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": True, "validated": True, "faithful": False},
        evidence_sufficiency={"verified": True, "necessary_ids": []},
    )
    assert report["stance"] == "abstain"
    assert any(r["code"] == "cf_not_dependent" for r in report["reasons"])

    exclude = compute_reliability(
        use_challenger=True,
        judge={"disposition": "exclude", "confidence": 0.8},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "exclude"},
        counterfactual={"performed": True, "validated": True, "faithful": False},
        evidence_sufficiency={"verified": True, "necessary_ids": []},
    )
    assert exclude["stance"] == "committed"


def test_ablation_does_not_abstain():
    result = compute_reliability(
        use_challenger=False,
        judge={"disposition": "exclude", "confidence": 0.1},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "exclude"},
    )
    assert result["stance"] == "committed"


def test_unverified_core_without_necessary_ids_is_soft_abstain():
    result = compute_reliability(
        use_challenger=True,
        judge={"disposition": "exclude", "confidence": 0.8},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "exclude"},
        counterfactual={"performed": False},
        evidence_sufficiency={"verified": False, "necessary_ids": []},
    )
    assert result["stance"] == "abstain"
    assert any(r["code"] == "evidence_core_unverified" and r["severity"] == "soft" for r in result["reasons"])

    with_core = compute_reliability(
        use_challenger=True,
        judge={"disposition": "suggest_report", "confidence": 0.8},
        judge_validation={"passed": True, "issues": []},
        baseline={"conclusion": "suggest_report"},
        counterfactual={"performed": True, "validated": True, "faithful": True},
        evidence_sufficiency={"verified": False, "necessary_ids": ["TX-1"]},
    )
    assert with_core["stance"] == "committed"
