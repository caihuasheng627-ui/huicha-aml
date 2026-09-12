from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.predicates import stub_challenger_item
from app.seed import seed_if_empty


def login_headers(client, staff_id="002183", password="aml123"):
    r = client.post("/api/auth/login", json={"staff_id": staff_id, "password": password})
    assert r.status_code == 200, r.text
    return {"X-Huicha-Session": r.json()["token"]}


@pytest.fixture()
def auth_headers(client):
    return login_headers(client)


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
        if "调查 Judge" in sys or "disposition" in sys:
            data = json.loads(user)
            findings = data.get("findings") or []
            codes = {f.get("code") for f in findings}
            if {"structuring", "funnel", "layering", "watchlist"} & codes:
                disposition, confidence = "suggest_report", 0.78
            elif "unregistered-counterparty" in codes:
                disposition, confidence = "observe", 0.62
            else:
                disposition, confidence = "exclude", 0.72
            support = [
                evidence_id
                for finding in findings
                if finding.get("polarity") == "support"
                for evidence_id in finding.get("evidence_ids", [])
            ][:6]
            counter = [
                evidence_id
                for finding in findings
                if finding.get("polarity") == "counter"
                for evidence_id in finding.get("evidence_ids", [])
            ][:6]
            cited = support or counter or data.get("allowed_evidence_ids", [])[:2]
            return (
                json.dumps(
                    {
                        "disposition": disposition,
                        "confidence": confidence,
                        "typologies": list(codes & {"structuring", "funnel", "layering", "watchlist"}),
                        "supporting_evidence_ids": support,
                        "contradicting_evidence_ids": counter,
                        "missing_evidence": [],
                        "rationale": [{"text": "单测 Judge 建议", "evidence_ids": cited}],
                        "next_actions": ["人工复核"],
                    },
                    ensure_ascii=False,
                ),
                usage,
            )
        if "完整四段调查底稿" in sys:
            data = json.loads(user)
            ids = "、".join(data.get("evidence_ids", [])[:4])
            conclusion = data["conclusion_label"]
            return (
                "\n".join(
                    [
                        f"【资金交易及客户行为】已核对证据 {ids}。",
                        f"【疑点分析】形成{conclusion}初步建议，证据 {ids}。",
                        f"【反证与缺失证据】已核查反向材料，证据 {ids}。",
                        f"【结论与理由】{conclusion}。须人工签发，不可自动报送，证据 {ids}。",
                    ]
                ),
                usage,
            )
        if "Challenger" in sys or "质疑" in sys or "delta" in sys or "predicate" in sys:
            try:
                data = json.loads(user)
            except Exception:
                data = {}
            item = stub_challenger_item(
                data if isinstance(data, dict) else {},
                claim="测试反证",
                detail="仅用于单测的 API 返回文案，不含虚构账号。",
                delta=-0.12,
            )
            return (
                json.dumps({"items": [item]}, ensure_ascii=False),
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
    monkeypatch.setenv("HUICHA_DATABASE_URL", "sqlite://")
    monkeypatch.setattr("app.llm.chat", fake_chat)
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.database.engine", engine)
    monkeypatch.setattr("app.database.SessionLocal", TestingSession)
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr("app.main.SessionLocal", TestingSession)
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
