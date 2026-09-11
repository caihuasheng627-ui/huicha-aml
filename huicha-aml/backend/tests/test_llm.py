from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from app.llm import _extract_json_array, _strip_fence, chat, llm_mode, normalize_challenger_items, validate_challenger_items


def test_normalize_keeps_predicate_and_args():
    rows = normalize_challenger_items(
        [
            {
                "claim": "过桥",
                "detail": "链",
                "evidence_ids": ["TX-L-01"],
                "predicate": "consecutive_transfer_chain",
                "args": {"tx_ids": ["TX-L-02", "TX-L-03"]},
                "delta": -0.1,
            }
        ]
    )
    assert rows[0]["predicate"] == "consecutive_transfer_chain"
    assert rows[0]["evidence_ids"] == ["TX-L-01", "TX-L-02", "TX-L-03"]


def test_stub_mode_chat(monkeypatch):
    monkeypatch.setenv("HUICHA_LLM_STUB", "1")
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False
    assert llm_mode() == "stub"
    text, usage = chat(
        [
            {"role": "system", "content": "你是反洗钱 Challenger。predicate 必填。"},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "transactions": [
                            {
                                "id": "TX-L-01",
                                "from_account": "A",
                                "to_account": "B",
                                "amount": 3,
                                "occurred_at": "2026-09-10 09:01:00",
                                "channel": "网银",
                            },
                            {
                                "id": "TX-L-02",
                                "from_account": "B",
                                "to_account": "C",
                                "amount": 2,
                                "occurred_at": "2026-09-10 09:07:00",
                                "channel": "网银",
                            },
                            {
                                "id": "TX-L-03",
                                "from_account": "C",
                                "to_account": "D",
                                "amount": 1,
                                "occurred_at": "2026-09-10 09:16:00",
                                "channel": "网银",
                            },
                        ],
                        "allowed_evidence_ids": ["TX-L-01", "TX-L-02", "TX-L-03"],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )
    items = _extract_json_array(text)
    assert items[0]["predicate"] == "consecutive_transfer_chain"
    assert usage["model"] == "stub"


def test_strip_fence_removes_language_tag():
    raw = "```text\n结论为排除。须人工签发。\n```"
    assert _strip_fence(raw) == "结论为排除。须人工签发。"


def test_extract_json_items_object():
    text = '{"items":[{"claim":"a","detail":"b","evidence_ids":["TX-1"],"delta":-0.1}]}'
    assert _extract_json_array(text)[0]["claim"] == "a"


def test_extract_json_ignores_bracket_in_preface():
    text = '[注] 以下为结果\n{"items":[{"claim":"经营抗辩","detail":"符合备货","evidence_ids":[],"delta":0}]}'
    items = _extract_json_array(text)
    assert items[0]["claim"] == "经营抗辩"


def test_validate_delta_bounds_and_evidence():
    items, total = validate_challenger_items(
        [{"claim": "x", "detail": "y", "evidence_ids": ["TX-1"], "delta": -0.5}],
        allowed_evidence={"TX-1"},
    )
    assert items == []
    assert total == 0.0
    items2, total2 = validate_challenger_items(
        [{"claim": "x", "detail": "y", "evidence_ids": ["NOPE"], "delta": -0.1}],
        allowed_evidence={"TX-1"},
    )
    assert items2 == []
    assert total2 == 0.0


def test_chat_timeout_becomes_runtime_error(monkeypatch):
    monkeypatch.delenv("HUICHA_LLM_STUB", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False

    def boom(*_a, **_k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="百炼网络错误"):
        chat([{"role": "user", "content": "hi"}])


def test_chat_http_error_becomes_runtime_error(monkeypatch):
    monkeypatch.delenv("HUICHA_LLM_STUB", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    import app.llm as llm_mod
    import urllib.error

    llm_mod._ENV_LOADED = False

    def boom(*_a, **_k):
        raise urllib.error.HTTPError(
            "https://example",
            400,
            "Bad Request",
            hdrs=None,
            fp=BytesIO(b'{"error":"bad model"}'),
        )

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError, match="百炼调用失败"):
        chat([{"role": "user", "content": "hi"}])


def test_chat_parses_usage(monkeypatch):
    monkeypatch.delenv("HUICHA_LLM_STUB", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False
    body = json.dumps(
        {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
    ).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", lambda *a, **k: mock_resp)

    text, usage = chat([{"role": "user", "content": "hi"}])
    assert text == "ok"
    assert usage["total_tokens"] == 3
