from app.checklist import (
    context_from_payload,
    format_item_line,
    generate_checklist,
    merge_note,
)


def _ctx(**overrides):
    base = {
        "alert": {"id": "ALT-X", "account_id": "6222-X", "alert_type": "拆分存入后集中转出", "created_at": "2026-09-10"},
        "customer": {
            "id": "C-X",
            "name": "演示客户",
            "kind": "individual",
            "kyc_level": "普通",
            "opened_at": "2025-07-01",
            "summary": "开户不足一年，职业登记为自由职业。",
        },
        "transactions": [
            {"id": "TX-1", "from_account": "CASH-01", "to_account": "6222-X", "amount": 49800, "remark": "存入"},
            {"id": "TX-2", "from_account": "6222-X", "to_account": "6222-OUT", "amount": 931200, "remark": "转出"},
        ],
        "counterparties": [
            {"account_id": "CASH-AGG", "label": "现金存入", "kind": "channel", "kyc_level": "缺失"},
            {"account_id": "6222-OUT", "label": "未核名对手方（演示）", "kind": "counterparty", "kyc_level": "缺失"},
        ],
        "recommendation": "REPORT_REVIEW",
        "conclusion": "suggest_report",
        "alert_type": "拆分存入后集中转出",
        "suspicious_types": ["structuring"],
        "elements_filled": 4,
        "elements_total": 5,
        "appended_ids": [],
    }
    base.update(overrides)
    return base


def test_incomplete_review_case_lists_missing_materials():
    items = generate_checklist(_ctx())
    by_id = {i["id"]: i for i in items}
    assert {i["id"] for i in items} == {
        "counterparty_kyc",
        "fund_purpose",
        "relationship_proof",
        "large_tx_voucher",
        "customer_edd",
    }
    missing = [i for i in items if i["status"] == "missing"]
    assert len(missing) >= 4
    assert by_id["counterparty_kyc"]["status"] == "missing"
    assert by_id["counterparty_kyc"]["category"] == "KYC"
    assert by_id["counterparty_kyc"]["priority"] == "high"
    assert by_id["fund_purpose"]["status"] == "missing"
    assert by_id["fund_purpose"]["category"] == "资金用途"
    assert by_id["relationship_proof"]["status"] == "missing"
    assert by_id["large_tx_voucher"]["status"] == "missing"
    assert by_id["customer_edd"]["status"] == "missing"
    assert all(i["reason"] and i["suggested_action"] for i in items)


def test_complete_exclude_case_is_not_all_missing():
    items = generate_checklist(
        _ctx(
            alert={"id": "ALT-A", "account_id": "6222-A", "alert_type": "大额频繁", "created_at": "2026-09-10"},
            customer={
                "id": "C-A",
                "name": "华东百货批发有限公司",
                "kind": "enterprise",
                "industry": "日用百货批发",
                "kyc_level": "普通",
                "opened_at": "2018-03-12",
                "summary": "主营日用百货分销，季节性备货特征明显。",
            },
            transactions=[
                {
                    "id": "TX-A-1",
                    "from_account": "6222-ST1",
                    "to_account": "6222-A",
                    "amount": 188000,
                    "remark": "货款-备货",
                },
                {
                    "id": "TX-A-2",
                    "from_account": "6222-A",
                    "to_account": "6222-SUP",
                    "amount": 154160,
                    "remark": "向上游采购",
                },
            ],
            counterparties=[
                {"account_id": "6222-ST1", "label": "余杭便利连锁", "kind": "counterparty", "kyc_level": "普通"},
                {"account_id": "6222-SUP", "label": "浙北日化供应中心", "kind": "counterparty", "kyc_level": "普通"},
            ],
            recommendation="CLOSE",
            conclusion="exclude",
            alert_type="大额频繁",
            suspicious_types=[],
            elements_filled=5,
            elements_total=5,
        )
    )
    missing = [i for i in items if i["status"] == "missing"]
    assert missing == []
    by_id = {i["id"]: i for i in items}
    assert by_id["fund_purpose"]["status"] == "satisfied"
    assert by_id["counterparty_kyc"]["status"] == "satisfied"
    assert by_id["customer_edd"]["status"] == "satisfied"


def test_relative_remark_satisfies_relationship():
    items = generate_checklist(
        _ctx(
            customer={
                "id": "C-D",
                "name": "李秀英",
                "kind": "individual",
                "kyc_level": "普通",
                "opened_at": "2012-01-08",
                "summary": "养老金入账为主，偶发大额为子女购房转账。",
            },
            transactions=[
                {
                    "id": "TX-D-01",
                    "from_account": "6222-D",
                    "to_account": "RELATIVE-01",
                    "amount": 300000,
                    "remark": "子女购房",
                }
            ],
            counterparties=[{"account_id": "RELATIVE-01", "label": "登记亲属", "kind": "counterparty", "kyc_level": "普通"}],
            recommendation="CLOSE",
            alert_type="大额转账",
            suspicious_types=[],
            elements_filled=5,
            elements_total=5,
        )
    )
    rel = next(i for i in items if i["id"] == "relationship_proof")
    assert rel["status"] == "satisfied"


def test_merge_note_is_idempotent_on_mark():
    item = {
        "id": "fund_purpose",
        "title": "资金用途说明",
        "category": "资金用途",
        "priority": "high",
        "reason": "备注多为存入。",
        "suggested_action": "索取用途说明。",
    }
    first = merge_note("", [item])
    assert first.startswith("【补证清单】")
    assert "资金用途说明" in first
    second = merge_note(first, [item])
    assert second.count("【补证清单】") == 1
    assert format_item_line(item) in second


def test_context_from_payload_reads_elements_and_reco():
    ctx = context_from_payload(
        {
            "alert": {"account_id": "6222-B"},
            "customer": {"name": "张启明"},
            "transactions": [{"from_account": "CASH-01", "to_account": "6222-B", "amount": 1, "remark": "存入"}],
            "case_v2": {"recommendation": "REPORT_REVIEW", "suspicious_types": ["structuring"]},
            "comparison": {"elements_filled": 3, "elements_total": 5},
            "checklist_appended": {"item_ids": ["fund_purpose"]},
            "graph": {"nodes": [{"id": "6222-B", "kind": "center"}, {"id": "CASH-AGG", "label": "现金存入", "kind": "channel"}]},
        }
    )
    assert ctx["recommendation"] == "REPORT_REVIEW"
    assert ctx["elements_filled"] == 3
    assert ctx["appended_ids"] == ["fund_purpose"]
    assert any(p["account_id"] == "CASH-AGG" for p in ctx["counterparties"])


def test_checklist_api_get_and_append(client):
    inv = client.post("/api/alerts/ALT-B-20260910/investigate", params={"use_challenger": True})
    assert inv.status_code == 200
    assert inv.json()["checklist"]["missing_count"] >= 1
    r = client.get("/api/alerts/ALT-B-20260910/checklist")
    assert r.status_code == 200
    body = r.json()
    assert body["alert_id"] == "ALT-B-20260910"
    assert body["missing_count"] >= 1
    missing = [i for i in body["items"] if i["status"] == "missing"]
    assert missing
    assert all({"id", "title", "category", "reason", "suggested_action", "status", "priority"} <= i.keys() for i in body["items"])
    assert body["recommendation"] in {"CLOSE", "MONITOR", "EDD", "REPORT_REVIEW"}

    alias = client.get("/api/cases/ALT-B-20260910/checklist")
    assert alias.status_code == 200
    assert alias.json()["missing_count"] == body["missing_count"]

    pick = [missing[0]["id"], missing[min(1, len(missing) - 1)]["id"]]
    pick = list(dict.fromkeys(pick))
    posted = client.post("/api/alerts/ALT-B-20260910/checklist/append", json={"item_ids": pick})
    assert posted.status_code == 200, posted.text
    out = posted.json()
    assert out["ok"] is True
    assert out["final_action"] == "draft_only"
    assert "自动报送" in out["note"]
    assert "【补证清单】" in out["human_note"]
    assert missing[0]["title"] in out["human_note"]
    detail = client.get("/api/alerts/ALT-B-20260910").json()
    assert "【补证清单】" in (detail.get("human_note") or "")
    assert "【补证备注】" in ((detail.get("investigation") or {}).get("report") or {}).get("full_text", "")

    again = client.get("/api/alerts/ALT-B-20260910/checklist").json()
    assert any(i["id"] in pick and i.get("appended") for i in again["items"])


def test_named_graph_peers_without_kyc_field_are_not_thin():
    items = generate_checklist(
        _ctx(
            recommendation="CLOSE",
            alert_type="大额频繁",
            suspicious_types=[],
            counterparties=[{"account_id": "6222-ST1", "label": "余杭便利连锁", "kind": "counterparty", "kyc_level": ""}],
            transactions=[{"id": "TX-A-1", "from_account": "6222-ST1", "to_account": "6222-A", "amount": 188000, "remark": "货款"}],
            elements_filled=5,
            elements_total=5,
            customer={
                "id": "C-A",
                "name": "华东百货",
                "kind": "enterprise",
                "kyc_level": "普通",
                "opened_at": "2018-03-12",
                "summary": "季节性备货。",
            },
        )
    )
    kyc = next(i for i in items if i["id"] == "counterparty_kyc")
    assert kyc["status"] == "satisfied"


def test_checklist_requires_draft(client):
    r = client.get("/api/alerts/ALT-C-20260910/checklist")
    assert r.status_code == 400
    missing = client.get("/api/alerts/NO-SUCH/checklist")
    assert missing.status_code == 404
    empty = client.post("/api/alerts/ALT-C-20260910/checklist/append", json={"item_ids": ["fund_purpose"]})
    assert empty.status_code == 400
    blank = client.post("/api/alerts/ALT-C-20260910/checklist/append", json={"item_ids": []})
    assert blank.status_code == 400
