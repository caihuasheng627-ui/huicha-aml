from app.tools import ALLOWED_TOOLS, alert_window, get_transactions, plan_tool_names, search_regulation


WRITE_TOOLS = {"update_transaction", "delete_customer", "file_str", "set_risk_rule"}


def test_allowed_tools_are_read_only():
    for name in WRITE_TOOLS:
        assert name not in ALLOWED_TOOLS
    for required in (
        "get_customer",
        "get_accounts",
        "get_transactions",
        "get_related_accounts",
        "get_network",
        "get_timeline",
        "search_regulation",
    ):
        assert required in ALLOWED_TOOLS


def test_planner_whitelist_only():
    names = plan_tool_names("拆分存入后集中转出")
    assert set(names) <= set(ALLOWED_TOOLS)
    assert "search_regulation" in names
    assert "get_baseline" not in names


def test_search_regulation_as_of_and_cite(client=None):
    hits = search_regulation("可疑交易报告", as_of="2026-09-10")
    assert hits
    assert all(h.get("id", "").startswith("KB-") for h in hits)
    assert all("source" in h for h in hits)
    empty = search_regulation("可疑交易报告", as_of="1990-01-01")
    assert empty == []


def test_accounts_and_timeline_from_db(client):
    # client fixture 已建库；用 API 间接验证工具在调查中被调用
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    tools = [t["tool"] for t in r.json()["tool_trace"]]
    assert "get_accounts" in tools
    assert "get_timeline" in tools
    assert "search_regulation" in tools
    times = [row["time"] for row in r.json()["timeline"]]
    assert any(t and t.startswith("2026-09-10 09:01") for t in times)


def test_transaction_window_excludes_old_and_keeps_alert_cluster(client):
    from app.database import SessionLocal
    from app.models import Transaction

    db = SessionLocal()
    try:
        if not db.get(Transaction, "TX-H-OLD"):
            db.add(
                Transaction(
                    id="TX-H-OLD",
                    from_account="POS-OLD",
                    to_account="6222-H-7701",
                    amount=1,
                    occurred_at="2020-01-01 10:00:00",
                    channel="POS",
                    remark="窗口外",
                )
            )
            db.commit()
        win = alert_window({"created_at": "2026-09-10 08:20:00"})
        rows = get_transactions(
            db,
            "6222-H-7701",
            window_start=win["start"],
            window_end=win["end"],
        )
        ids = {t["id"] for t in rows}
        assert "TX-H-OLD" not in ids
        assert any(i.startswith("TX-H-CASH") for i in ids)
        all_rows = get_transactions(db, "6222-H-7701")
        assert "TX-H-OLD" in {t["id"] for t in all_rows}
    finally:
        db.close()
