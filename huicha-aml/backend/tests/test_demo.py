from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app, format_cn
from app.seed import seed_if_empty
from app.tools import amount_known_forms, fact_check, yuan


@pytest.fixture()
def client(monkeypatch):
    def fake_chat(messages, *, temperature=0.0, max_tokens=900):
        user = messages[-1]["content"]
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cached": False,
            "model": "deepseek-v4-flash-0731",
        }
        sys = messages[0]["content"]
        if "Challenger" in sys or "质疑" in sys or "delta" in sys:
            try:
                data = json.loads(user)
                eids = (data.get("allowed_evidence_ids") or ["TX-A-IN-01"])[:2]
            except Exception:
                eids = ["TX-A-IN-01"]
            return (
                json.dumps(
                    {
                        "items": [
                            {
                                "claim": "测试反证",
                                "detail": "仅用于单测的 API 返回文案，不含虚构账号。",
                                "evidence_ids": eids,
                                "delta": -0.12,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                usage,
            )
        data = json.loads(user)
        text = (
            f"结论为{data['conclusion']}。"
            f"客户{data['customer_name']}（{data['customer_id']}，账户{data['account_id']}）"
            f"相关交易编号：{data['allowed_tx_ids']}。须人工签发，不可自动报送。"
        )
        return text, usage

    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-not-used")
    monkeypatch.setenv("DASHSCOPE_MODEL", "deepseek-v4-flash-0731")
    monkeypatch.setattr("app.llm.chat", fake_chat)
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    seed_if_empty(db)
    db.close()

    def _override():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


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


def test_amount_known_forms_include_wan():
    forms = amount_known_forms(188000)
    assert any("万元" in f for f in forms)


@pytest.mark.parametrize(
    "alert_id,use_challenger,expected",
    [
        ("ALT-A-20260910", True, "exclude"),
        ("ALT-A-20260910", False, "suggest_report"),
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
    assert data["llm"]["model"] == "deepseek-v4-flash-0731"
    assert data["llm"]["masked"] is True
    assert data["scoring"]["llm_delta"] <= 0.15
    assert data["tool_trace"], "tool_trace 应来自真实 @tool 调用"
    assert any(t["tool"] == "get_alert" for t in data["tool_trace"])
    if use_challenger:
        assert data["challenger"]
        assert data["challenger"][0].get("claim") == "测试反证" or data["challenger"][0].get("title") == "测试反证"
    assert "须人工签发" in data["report"]["reason"]
    assert "manual_minutes" not in data["comparison"]


def test_hallucination_blocks_sign(client):
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
    )
    assert blocked.status_code == 400
    ok = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "modify", "note": "已人工删除幻觉账号"},
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


def test_feedback_endpoint(client):
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    client.post("/api/alerts/ALT-A-20260910/decide", json={"decision": "confirm", "note": ""})
    r = client.get("/api/feedback")
    assert r.status_code == 200
    assert r.json()["decisions"]["confirm"] >= 1


def test_labeled_corpus_size(client):
    r = client.get("/api/metrics")
    assert r.json()["labeled"] >= 30


def test_health_reports_llm(client):
    r = client.get("/api/health")
    assert r.json()["llm"] == "bailian"
