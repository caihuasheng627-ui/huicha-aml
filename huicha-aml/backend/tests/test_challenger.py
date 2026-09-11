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
    kept, total, _ = filter_challenger_items(
        [{"claim": "经营解释", "evidence_ids": ["TX-1"], "delta": -0.10}],
        allowed={"TX-1"},
    )
    assert kept[0]["delta"] == -0.10
    assert total == -0.10


def test_pipeline_records_rejected(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    data = r.json()
    assert "rejected_claims" in data
    assert abs(data["scoring"]["llm_delta"]) <= 0.15
    roles = [s["role"] for s in data["steps"]]
    assert "Challenger" in roles
    assert "Validator" in roles
