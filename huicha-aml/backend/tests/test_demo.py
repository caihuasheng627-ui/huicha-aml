from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.main import format_cn
from app.tools import amount_known_forms, fact_check, yuan


def test_fact_check_catches_fake_wan_yuan():
    facts = {
        "amounts": [188000.0],
        "tx_ids": ["TX-A-IN-01"],
        "accounts": ["6222-A-8801"],
        "dates": ["2026-09-10"],
        "names": ["华东百货批发有限公司", "C-A"],
    }
    assert fact_check(f"金额{yuan(188000).strip()}", facts) == []
    issues = fact_check("另发现金额 88.88 万元 转出", facts)
    assert any("88.88" in i["token"] for i in issues)
    issues2 = fact_check("对手账户 6222-FAKE-9999", facts)
    assert any(i["token"] == "6222-FAKE-9999" for i in issues2)


def test_fact_check_allows_llm_threshold_and_approx_phrasing():
    facts = {
        "amounts": [188000.0],
        "tx_ids": ["TX-A-IN-01"],
        "accounts": ["6222-A-8801"],
        "dates": ["2026-09-10"],
        "names": ["华东百货批发有限公司"],
        "kb_ids": ["KB-REG-01"],
    }
    assert fact_check("大额申报阈值为 5 万元,本案无接近阈值的拆分特征。", facts) == []
    assert fact_check("月度流入约 200 万元量级。", facts) == []
    issues = fact_check("另转出 88.88 万元至陌生账户。", facts)
    assert any("88.88" in i["token"] for i in issues)
    issues20 = fact_check("另转出 20 万元至陌生账户。", facts)
    assert any("20" in i["token"] for i in issues20)


def test_fact_check_treats_alert_and_evidence_ids_as_whole_tokens():
    facts = {
        "amounts": [],
        "tx_ids": ["TX-B-IN-01"],
        "accounts": [],
        "dates": ["2026-09-10"],
        "names": [],
        "ref_ids": ["ALT-B-20260910", "EV-ALT-B-20260910-001"],
    }
    assert fact_check("告警编号ALT-B-20260910，证据EV-ALT-B-20260910-001，日期20260910。", facts) == []
    issues = fact_check("证据 EV-ALT-B-20260910-999 与告警 ALT-Z-20260910。", facts)
    assert {i["token"] for i in issues} == {"EV-ALT-B-20260910-999", "ALT-Z-20260910"}


def test_sanitize_missing_evidence_drops_ids_and_ranges():
    from app.decision import normalize_judge, sanitize_missing_evidence

    kept, dropped = sanitize_missing_evidence(
        ["EV-ALT-B-20260910-001", "TX-B-IN-02", "C-B", "KB-REG-01", "EV-X-1至EV-X-9", "贸易合同", "贸易合同", ""],
        known_ids={"KB-REG-01"},
    )
    assert kept == ["贸易合同"]
    assert len(dropped) == 5
    decision = normalize_judge(
        {
            "disposition": "observe",
            "confidence": 0.5,
            "missing_evidence": ["ACCOUNT_002", "受益所有人信息"],
            "rationale": [{"text": "x", "evidence_ids": ["TX-1"]}],
        }
    )
    assert decision["missing_evidence"] == ["受益所有人信息"]
    assert decision["sanitized_missing_evidence"] == ["ACCOUNT_002"]


def test_parse_model_json_reports_truncation():
    from app.llm import _parse_model_json

    with pytest.raises(RuntimeError, match="截断"):
        _parse_model_json('{"disposition": "observe", "rationale": [', {"finish_reason": "length", "completion_tokens": 1000}, role="Judge")
    with pytest.raises(RuntimeError, match="非 JSON"):
        _parse_model_json("不是 JSON", {"finish_reason": "stop"}, role="Judge")
    assert _parse_model_json('```json\n{"a": 1}\n```', {"finish_reason": "stop"}, role="Judge") == {"a": 1}


def test_amount_known_forms_include_wan():
    forms = amount_known_forms(188000)
    assert any("万元" in f for f in forms)


@pytest.mark.parametrize(
    "alert_id,use_challenger,expected",
    [
        ("ALT-A-20260910", True, "exclude"),
        ("ALT-A-20260910", False, "exclude"),
        ("ALT-B-20260910", True, "suggest_report"),
        ("ALT-C-20260910", True, "suggest_report"),
        ("ALT-D-20260909", True, "exclude"),
        ("ALT-F-20260910", True, "observe"),
    ],
)
def test_demo_conclusions(client, alert_id, use_challenger, expected):
    r = client.post(
        f"/api/alerts/{alert_id}/investigate",
        params={"use_challenger": use_challenger, "inject_hallucination": False},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["conclusion"] == expected
    assert data["confidence_kind"] == (
        "llm_self_assessed_not_calibrated" if use_challenger else "rule_score_not_calibrated"
    )
    assert data["llm"]["model"] == "deepseek-v4-flash-0731"
    assert data["llm"]["masked"] is True
    assert data["scoring"]["mode"] == "judge_not_additive"
    assert data["scoring"]["llm_delta"] == 0.0
    assert data["tool_trace"], "tool_trace 应来自真实 @tool 调用"
    assert any(t["tool"] == "get_alert" for t in data["tool_trace"])
    if use_challenger:
        assert data["judge"]["rationale"]
        assert data["judge_validation"]["passed"] is True
    assert "须人工签发" in data["report"]["reason"]
    assert "manual_minutes" not in data["comparison"]


def test_hallucination_blocks_sign(client, auth_headers):
    r = client.post(
        "/api/alerts/ALT-A-20260910/investigate",
        params={"use_challenger": True, "inject_hallucination": True},
    )
    data = r.json()
    assert data["can_sign"] is False
    assert any(i["token"] == "6222-FAKE-9999" for i in data["fact_issues"])
    blocked = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": ""},
        headers=auth_headers,
    )
    assert blocked.status_code == 400
    ok = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "modify", "note": "已人工删除幻觉账号"},
        headers=auth_headers,
    )
    assert ok.status_code == 200


def test_findings_use_graph_labels_not_hardcoded(client):
    r = client.post(
        "/api/alerts/ALT-A-20260910/investigate",
        params={"use_challenger": True, "inject_hallucination": False},
    )
    data = r.json()
    blob = " ".join(f["detail"] for f in data["findings"])
    assert "余杭便利连锁" in blob or "浙北日化" in blob


def test_audit_time_is_cn_local(client, monkeypatch):
    frozen = datetime(2026, 9, 10, 4, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.main.utcnow", lambda: frozen.replace(tzinfo=None))
    client.post(
        "/api/alerts/ALT-B-20260910/investigate",
        params={"use_challenger": True, "inject_hallucination": False},
    )
    d = client.get("/api/alerts/ALT-B-20260910").json()
    assert d["audit"]
    assert any(a["action"].startswith("tool:") for a in d["audit"])
    ts = [a for a in d["audit"] if a["action"] == "investigate"][-1]["created_at"]
    assert ts == "2026-09-10 12:00:00"
    assert format_cn(frozen.replace(tzinfo=None)) == "2026-09-10 12:00:00"


def test_feedback_endpoint(client, auth_headers):
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": ""},
        headers=auth_headers,
    )
    r = client.get("/api/feedback")
    assert r.status_code == 200
    assert r.json()["decisions"]["confirm"] >= 1


def test_labeled_corpus_size(client):
    r = client.get("/api/metrics")
    body = r.json()
    assert body["labeled"] >= 80
    assert "模板" in body["labeled_note"]
    assert body["store"] == "sqlite"


def test_health_reports_llm(client):
    r = client.get("/api/health")
    body = r.json()
    assert body["llm"] == "bailian"
    assert body["auth"] in {"off", "demo_token"}
    assert "*" not in body["cors"]
    assert body["kb_docs"] >= 15
    assert body["kb_retrieval"] == "keyword-overlap"
    assert body["limitations"]


def test_planner_skips_watchlist_on_wholesale(client):
    r = client.post(
        "/api/alerts/ALT-A-20260910/investigate",
        params={"use_challenger": True, "inject_hallucination": False},
    )
    assert r.status_code == 200, r.text
    tools = [t["tool"] for t in r.json()["tool_trace"]]
    assert "get_baseline" in tools
    assert "get_graph" in tools
    assert "check_watchlist" not in tools


def test_planner_skips_baseline_on_structuring(client):
    r = client.post(
        "/api/alerts/ALT-B-20260910/investigate",
        params={"use_challenger": True, "inject_hallucination": False},
    )
    assert r.status_code == 200, r.text
    tools = [t["tool"] for t in r.json()["tool_trace"]]
    assert "get_baseline" not in tools
    assert "get_graph" in tools
    assert "check_watchlist" in tools


def test_migrate_sqlite_adds_gold_label(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from app.database import migrate_sqlite

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE alerts (id VARCHAR PRIMARY KEY, title VARCHAR)"))
    assert "gold_label" in migrate_sqlite(eng)[0]
    cols = {c["name"] for c in inspect(eng).get_columns("alerts")}
    assert "gold_label" in cols
    assert migrate_sqlite(eng) == []
