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
