from app.tools import ALLOWED_TOOLS, plan_tool_names, search_regulation


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
