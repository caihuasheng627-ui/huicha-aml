from app.attack_demo import ATTACKS, context_from_payload, list_attacks, run_attacks


def _facts_payload():
    return {
        "alert": {"id": "ALT-B-20260910", "account_id": "6222-B-1908"},
        "customer": {"id": "C-B", "name": "演示个人"},
        "transactions": [
            {
                "id": "TX-B-IN-01",
                "from_account": "CASH-01",
                "to_account": "6222-B-1908",
                "amount": 49800,
                "occurred_at": "2026-09-02 09:11:00",
                "channel": "ATM/现金",
            },
            {
                "id": "TX-B-IN-02",
                "from_account": "CASH-02",
                "to_account": "6222-B-1908",
                "amount": 49800,
                "occurred_at": "2026-09-03 09:12:00",
                "channel": "ATM/现金",
            },
            {
                "id": "TX-B-IN-03",
                "from_account": "CASH-03",
                "to_account": "6222-B-1908",
                "amount": 49000,
                "occurred_at": "2026-09-04 09:13:00",
                "channel": "ATM/现金",
            },
        ],
        "evidence": [{"id": "EV-B-1"}],
        "kb_hits": [{"id": "KB-REG-01"}],
    }


def test_catalog_size_and_fields():
    items = list_attacks()
    assert 8 <= len(items) <= 20
    ids = [a["id"] for a in ATTACKS]
    assert ids == [i["id"] for i in items]
    assert len(set(ids)) == len(ids)
    for it in items:
        assert it["title"] and it["attack_type"] and it["expected_reason_category"]
        assert it["claim"] or it["id"] == "ATK-12"


def test_each_fixture_rejected_on_synthetic_case_b():
    ctx = context_from_payload(
        _facts_payload(),
        case_id="ALT-B-20260910",
        evidence_case={"TX-A-IN-01": "ALT-A-20260910", "TX-B-IN-01": "ALT-B-20260910"},
    )
    rows = run_attacks(None, ctx)
    assert len(rows) == len(ATTACKS)
    for row in rows:
        assert row["rejected"], f"{row['id']} 应被 Validator 拒绝，实际 Accept：{row}"
        assert row["matched_expected"], f"{row['id']} 原因类别不符：{row['reason']}"


def test_list_attacks_api(client):
    r = client.get("/api/attacks")
    assert r.status_code == 200
    data = r.json()
    assert 8 <= len(data["items"]) <= 20
    assert "Validator" in data["note"]


def test_run_requires_draft(client):
    r = client.post("/api/alerts/ALT-B-20260910/attacks/run", json={"run_all": True})
    assert r.status_code == 400
    assert "调查草稿" in r.json()["detail"]


def test_unknown_attack_id(client):
    inv = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert inv.status_code == 200
    r = client.post("/api/alerts/ALT-B-20260910/attacks/run", json={"attack_id": "ATK-NOPE"})
    assert r.status_code == 404


def test_run_all_against_real_validator(client):
    inv = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert inv.status_code == 200
    r = client.post("/api/alerts/ALT-B-20260910/attacks/run", json={"run_all": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == len(ATTACKS)
    assert data["intercepted"] == len(ATTACKS)
    assert data["items"]
    for it in data["items"]:
        assert it["rejected"], f"{it['id']} 应 Reject：{it}"
        assert it["matched_expected"], f"{it['id']} 原因不符：{it['reason']}"
        assert it["reason"]


def test_run_one_and_cases_alias(client):
    inv = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert inv.status_code == 200
    one = client.post("/api/alerts/ALT-B-20260910/attacks/run", json={"attack_id": "ATK-01"})
    assert one.status_code == 200
    row = one.json()["items"][0]
    assert row["id"] == "ATK-01"
    assert row["rejected"]
    assert "超出" in row["reason"]
    alias = client.post("/api/cases/ALT-B-20260910/attacks/run", json={"attack_id": "ATK-05"})
    assert alias.status_code == 200
    cross = alias.json()["items"][0]
    assert cross["rejected"]
    assert "跨案件" in cross["reason"]
