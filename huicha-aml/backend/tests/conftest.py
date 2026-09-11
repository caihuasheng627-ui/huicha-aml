from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.seed import seed_if_empty


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
