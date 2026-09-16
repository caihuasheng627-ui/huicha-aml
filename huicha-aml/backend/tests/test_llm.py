from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from app.llm import _extract_json_array, _strip_fence, chat, llm_mode, normalize_challenger_items, validate_challenger_items
from app.privacy import PrivacyLeakError


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


def test_stub_chat_blocks_raw_account_token(monkeypatch):
    monkeypatch.setenv("HUICHA_LLM_STUB", "1")
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False
    with pytest.raises(PrivacyLeakError, match="6222-A-8801"):
        chat([{"role": "user", "content": "对手 6222-A-8801"}])


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
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
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
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
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
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
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


def test_usage_and_investigation_tokens():
    from app.llm import investigation_tokens, usage_tokens

    assert usage_tokens(None) == 0
    assert usage_tokens({"prompt_tokens": 10, "completion_tokens": 20}) == 30
    assert usage_tokens({"total_tokens": 12, "prompt_tokens": 1}) == 12
    assert investigation_tokens({"comparison": {"tokens": 48}}) == 48
    assert investigation_tokens({
        "llm": {"usage": {"judge": {"total_tokens": 10}, "reporter": {"prompt_tokens": 2, "completion_tokens": 3}}},
    }) == 15


def _judge_inputs() -> dict:
    return {
        "alert": {"alert_type": "大额转账", "upstream": "monitoring"},
        "customer": {"id": "C-1", "name": "客户", "kind": "individual", "industry": "个人-受雇"},
        "findings": [{"code": "thin", "title": "t", "detail": "d", "evidence_ids": ["TX-1"], "polarity": "counter"}],
        "transactions": [],
        "baseline": {},
        "kb_hits": [],
        "allowed_evidence": ["TX-1"],
    }


def test_enrich_judge_uses_product_prompt_version_by_default(monkeypatch):
    import app.llm as llm_mod
    from app.prompts import PROMPTS, prompt_version

    seen: dict = {}

    def fake_chat(messages, **kwargs):
        seen["system"] = messages[0]["content"]
        return json.dumps({"disposition": "exclude", "confidence": 0.9}), {"finish_reason": "stop"}

    monkeypatch.setattr(llm_mod, "chat", fake_chat)
    data, _ = llm_mod.enrich_judge(db=None, **_judge_inputs())
    assert data["disposition"] == "exclude"
    assert prompt_version("judge") == "judge_v3"
    assert seen["system"] == PROMPTS["judge_v3"]
    assert "三档判定标准" in seen["system"]

    llm_mod.enrich_judge(db=None, prompt_kind="judge_v2", **_judge_inputs())
    assert seen["system"] == PROMPTS["judge_v2"]

    llm_mod.enrich_judge(db=None, prompt_kind="judge_v4", **_judge_inputs())
    assert seen["system"] == PROMPTS["judge_v4"]
    assert prompt_version("judge") == "judge_v3"


def test_result_source_key_namespaces_non_deepseek_models():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments"))
    import benchmark as bench

    deepseek = {"source": "narrative_vignette_blind_struct", "model": "deepseek-v4-flash-0731"}
    glm = {"source": "narrative_vignette_blind_struct", "model": "glm-5.2"}
    official = {"source": "narrative_vignette_blind_struct", "model": "deepseek-chat"}
    assert bench._result_source_key(deepseek) == "narrative_vignette_blind_struct"
    assert bench._result_source_key(glm) == "narrative_vignette_blind_struct__glm-5.2"
    assert bench._result_source_key(official) == "narrative_vignette_blind_struct__deepseek-chat"


def test_zhipu_key_routes_to_glm52(monkeypatch):
    import app.llm as llm_mod

    monkeypatch.delenv("HUICHA_LLM_STUB", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_MODEL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-zhipu-test")
    llm_mod._ENV_LOADED = False
    assert llm_mod.require_api_key() == "sk-zhipu-test"
    assert llm_mod.llm_model() == "glm-5.2"
    assert "bigmodel.cn" in llm_mod.llm_base_url()
    assert llm_mod.llm_mode() == "zhipu"


def test_deepseek_official_key_routes_to_deepseek_chat(monkeypatch):
    import app.llm as llm_mod

    monkeypatch.delenv("HUICHA_LLM_STUB", raising=False)
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-bailian-unused")
    monkeypatch.setenv("DASHSCOPE_MODEL", "qwen3.7-flash")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    llm_mod._ENV_LOADED = False
    assert llm_mod.require_api_key() == "sk-deepseek-test"
    assert llm_mod.llm_model() == "deepseek-chat"
    assert "deepseek.com" in llm_mod.llm_base_url()
    assert llm_mod.llm_mode() == "deepseek"


def test_judge_v4_is_ablation_only_and_avoids_v3_exemplars():
    from app.prompts import PROMPTS, prompt_version

    assert prompt_version("judge") == "judge_v3"
    assert "judge_v4" in PROMPTS
    exemplars = (
        "工资表",
        "赔付书",
        "财政",
        "监管放款",
        "监管账户",
        "网签",
        "合同",
        "公证书",
        "用途说明",
        "发票",
        "取现",
        "回流",
        "多层",
        "递减",
        "过桥",
        "关联",
        "对倒",
        "闭环",
        "现金",
        "兑换商",
        "归集",
        "集中外转",
        "阈值",
        "存入",
    )
    body = PROMPTS["judge_v4"]
    for token in exemplars:
        assert token not in body, token
    assert "口头陈述前后不一致" in body
    assert "不得单独把结论从 observe 升为 suggest_report" in body


def test_enrich_judge_rejects_unknown_prompt_kind(monkeypatch):
    import app.llm as llm_mod

    monkeypatch.setattr(llm_mod, "chat", lambda *a, **k: ("{}", {}))
    with pytest.raises(ValueError):
        llm_mod.enrich_judge(db=None, prompt_kind="reporter_v3", **_judge_inputs())
    with pytest.raises(ValueError):
        llm_mod.enrich_judge(db=None, prompt_kind="judge_v99", **_judge_inputs())
