from app.evidence_sufficiency import MAX_CANDIDATES, MAX_ROUNDS, search_minimal_set


def _judge(support):
    return {
        "disposition": "suggest_report",
        "supporting_evidence_ids": support,
        "rationale": [{"text": "t", "evidence_ids": support[:1]}],
    }


def _findings(clusters):
    return [
        {"code": f"c{i}", "title": f"f{i}", "polarity": "support", "evidence_ids": ids}
        for i, ids in enumerate(clusters)
    ]


def test_necessary_cluster_kept_redundant_dropped():
    judge = _judge(["TX-1", "TX-2", "TX-3"])
    findings = _findings([["TX-1"], ["TX-2"], ["TX-3"]])

    def run_round(removed, _message):
        if "TX-1" in removed:
            return {"judge": {"disposition": "observe"}, "validation": {"passed": True, "issues": []}}
        return {"judge": {"disposition": "suggest_report"}, "validation": {"passed": True, "issues": []}}

    sufficiency, first = search_minimal_set(judge=judge, findings=findings, verified_claims=[], run_round=run_round)
    assert "TX-1" in sufficiency["necessary_ids"]
    assert "TX-2" in sufficiency["redundant_ids"] or "TX-3" in sufficiency["redundant_ids"]
    assert first["faithful"] is True
    assert sufficiency["method"] == "bounded_greedy"
    assert sufficiency["verified"] is True


def test_budget_exhausted_sets_verified_false():
    support = [f"TX-{i}" for i in range(1, 8)]
    judge = _judge(support)
    findings = _findings([[eid] for eid in support])

    def run_round(_removed, _message):
        return {"judge": {"disposition": "observe"}, "validation": {"passed": True, "issues": []}}

    sufficiency, _ = search_minimal_set(
        judge=judge,
        findings=findings,
        verified_claims=[],
        run_round=run_round,
        max_candidates=MAX_CANDIDATES,
        max_rounds=MAX_ROUNDS,
    )
    assert sufficiency["budget_exhausted"] is True
    assert sufficiency["verified"] is False
    assert sufficiency["rounds"] <= MAX_ROUNDS


def test_cf_abstain_marks_cluster_necessary():
    judge = _judge(["TX-1", "TX-2"])
    findings = _findings([["TX-1"], ["TX-2"]])

    def run_round(_removed, _message):
        return {
            "judge": {"disposition": "suggest_report", "confidence": 0.4},
            "validation": {"passed": True, "issues": []},
        }

    sufficiency, _ = search_minimal_set(
        judge=judge,
        findings=findings,
        verified_claims=[],
        run_round=run_round,
        baseline={"conclusion": "exclude"},
    )
    assert "TX-1" in sufficiency["necessary_ids"]
    assert "TX-1" not in sufficiency["redundant_ids"]
