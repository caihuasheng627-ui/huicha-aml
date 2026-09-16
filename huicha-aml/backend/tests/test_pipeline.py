from __future__ import annotations

import json

from app.pipeline.toolkit import execute_judge_tool, judge_tools_enabled


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        raw = "\n".join(data_lines)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = raw
        events.append({"event": event, "data": data})
    return events


def test_investigate_payload_includes_trace_and_models(client):
    r = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    roles = [t["role"] for t in data["trace"]]
    for role in ("Planner", "Collector", "Privacy", "Analyst", "Judge", "Skeptic", "PolicyGuardrail", "Reporter"):
        assert role in roles
    assert data["llm"]["model"] == "deepseek-v4-flash-0731"
    assert data["llm"]["models"]["judge"] == "deepseek-v4-flash-0731"
    assert data["llm"]["models"]["reporter"] == "deepseek-v4-flash-0731"
    assert data["prompt_versions"]["judge"] == "judge_v3p"
    assert data["comparison"]["tokens"] >= 0
    assert data["llm"]["usage"]["total_tokens"] == data["comparison"]["tokens"]


def test_investigate_stream_emits_stages_and_done(client):
    post = client.post("/api/alerts/ALT-C-20260910/investigate", params={"use_challenger": True})
    assert post.status_code == 200, post.text
    streamed = client.get("/api/alerts/ALT-A-20260910/investigate/stream", params={"use_challenger": True})
    assert streamed.status_code == 200, streamed.text
    assert "text/event-stream" in streamed.headers.get("content-type", "")
    events = _parse_sse(streamed.text)
    kinds = [e["event"] for e in events]
    assert "done" in kinds
    started_roles = [
        e["data"].get("role")
        for e in events
        if e["event"] == "stage" and e["data"].get("status") == "started"
    ]
    for role in ("Planner", "Collector", "Privacy", "Analyst", "Judge", "Skeptic", "PolicyGuardrail", "Reporter"):
        assert role in started_roles
    done = next(e["data"]["payload"] for e in events if e["event"] == "done")
    assert set(post.json()) <= set(done)
    assert done["alert"]["id"] == "ALT-A-20260910"
    assert done["prompt_versions"]["judge"] == "judge_v3p"


def test_llm_model_role_override(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_MODEL", "deepseek-v4-flash-0731")
    monkeypatch.setenv("HUICHA_MODEL_JUDGE", "qwen-judge")
    monkeypatch.delenv("HUICHA_MODEL_REPORTER", raising=False)
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False
    assert llm_mod.llm_model() == "deepseek-v4-flash-0731"
    assert llm_mod.llm_model("judge") == "qwen-judge"
    assert llm_mod.llm_model("reporter") == "deepseek-v4-flash-0731"


def test_judge_tools_disabled_by_default():
    assert judge_tools_enabled() is False


def test_judge_tools_round_and_cross_account_denied(client, monkeypatch):
    monkeypatch.setenv("HUICHA_JUDGE_TOOLS", "1")
    import app.llm as llm_mod

    orig = llm_mod.chat
    calls = {"n": 0}

    def wrap(messages, *, temperature=0.0, max_tokens=900, model=None, tools=None, **_kwargs):
        sys = messages[0]["content"] if messages else ""
        is_judge = "调查 Judge" in sys or "disposition" in sys
        if is_judge and tools:
            n = calls["n"]
            calls["n"] += 1
            if n == 0:
                return (
                    "",
                    {
                        "tool_calls": [
                            {
                                "id": "call-deny",
                                "type": "function",
                                "function": {
                                    "name": "get_related_accounts",
                                    "arguments": json.dumps({"account_id": "6222-FAKE-9999"}),
                                },
                            }
                        ],
                        "cached": False,
                        "total_tokens": 4,
                    },
                )
            if n == 1:
                return (
                    "",
                    {
                        "tool_calls": [
                            {
                                "id": "call-ok",
                                "type": "function",
                                "function": {
                                    "name": "get_related_accounts",
                                    "arguments": json.dumps({"account_id": "6222-L-B"}),
                                },
                            }
                        ],
                        "cached": False,
                        "total_tokens": 4,
                    },
                )
        if is_judge and len(messages) > 2:
            return orig(messages[:2], temperature=temperature, max_tokens=max_tokens)
        return orig(messages, temperature=temperature, max_tokens=max_tokens, model=model, tools=tools)

    monkeypatch.setattr(llm_mod, "chat", wrap)
    r = client.post("/api/alerts/ALT-L-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200, r.text
    data = r.json()
    tools = data["tool_trace"]
    assert any(t["tool"] == "get_related_accounts" and t.get("ok") is False and "跨账户" in (t.get("error") or "") for t in tools)
    assert any(t["tool"] == "get_related_accounts" and t.get("ok") is True for t in tools)
    assert data["judge_validation"]["passed"] is True
    assert calls["n"] >= 2


def test_execute_judge_tool_rejects_unknown_and_cross_account(client):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        denied, ids, txs = execute_judge_tool(
            "delete_customer",
            {},
            db=db,
            account_id="6222-L-B",
            as_of="2026-09-10",
            alert_type="x",
            industry="y",
            search_knowledge=lambda *a, **k: [],
        )
        assert "白名单" in str(denied)
        denied2, _, _ = execute_judge_tool(
            "get_transactions",
            {"account_id": "6222-OTHER"},
            db=db,
            account_id="6222-L-B",
            as_of="2026-09-10",
            alert_type="x",
            industry="y",
            search_knowledge=lambda *a, **k: [],
        )
        assert "主体账户" in str(denied2)
        assert ids == [] and txs == []
    finally:
        db.close()
