import json

import pytest

from app.logging_util import redact
from app.privacy import PrivacyLeakError, PrivacyMap, inspect_outbound


def test_privacy_masks_to_client_account():
    p = PrivacyMap()
    assert p.register_name("华东百货批发有限公司") == "CLIENT_001"
    assert p.register_account("6222-A-8801") == "ACCOUNT_001"
    text = p.mask_text("华东百货批发有限公司账户 6222-A-8801")
    assert "华东" not in text
    assert "6222-A-8801" not in text
    assert "CLIENT_001" in text
    assert "ACCOUNT_001" in text
    assert p.unmask_text(text) == "华东百货批发有限公司账户 6222-A-8801"
    assert p.register_account("UNK-REL-09") == "UNK-REL-09"
    assert p.register_account("RELATIVE-01") == "RELATIVE-01"


def test_customer_id_gets_cust_placeholder():
    p = PrivacyMap()
    assert p.register_customer_id("C-H") == "CUST_001"
    assert p.register_account("C-A") == "CUST_002"
    assert p.register_account("6222-H-7701") == "ACCOUNT_001"
    blob = p.mask_text("客户 C-H 账户 6222-H-7701")
    assert "C-H" not in blob
    assert "6222-H-7701" not in blob
    assert p.unmask_text(blob) == "客户 C-H 账户 6222-H-7701"


def test_prepare_for_llm_drops_city_and_asserts_clean():
    p = PrivacyMap()
    p.register_name("张启明")
    p.register_account("6222-B-1908")
    p.register_customer_id("C-B")
    out = p.prepare_for_llm(
        {
            "customer": {"id": "C-B", "name": "张启明", "city": "南昌", "industry": "个人-无固定职业"},
            "account": "6222-B-1908",
        }
    )
    assert out["customer"]["name"] == "CLIENT_001"
    assert out["customer"]["id"] == "CUST_001"
    assert out["account"] == "ACCOUNT_001"
    assert "city" not in out["customer"]
    assert p.egress_calls == 1
    assert p.receipt()["policy"] == "privacy_v2"


def test_assert_clean_rejects_raw_name():
    p = PrivacyMap()
    p.register_name("华东百货批发有限公司")
    with pytest.raises(PrivacyLeakError, match="未脱敏"):
        p.assert_clean({"customer": "华东百货批发有限公司"})


def test_inspect_outbound_blocks_account_token():
    with pytest.raises(PrivacyLeakError, match="6222-A-8801"):
        inspect_outbound([{"role": "user", "content": "账户 6222-A-8801"}])
    inspect_outbound([{"role": "user", "content": "账户 ACCOUNT_001"}])


def test_logs_redact_account_like_tokens():
    assert "6222-A-8801" not in redact("调查 6222-A-8801")
    assert "[REDACTED]" in redact("调查 6222-A-8801")
    assert "有限公司" not in redact("华东百货批发有限公司开户")
    assert "生成调查草稿" in redact("生成调查草稿")


def test_case_h_llm_context_has_no_raw_pii(client, monkeypatch):
    import app.llm as llm_mod

    captured = {}
    orig = llm_mod.chat

    def wrap(messages, *, temperature=0.0, max_tokens=900):
        sys = messages[0]["content"]
        user = messages[-1]["content"]
        if ("调查 Judge" in sys or "disposition" in sys) and "ctx" not in captured:
            captured["ctx"] = json.loads(user)
        return orig(messages, temperature=temperature, max_tokens=max_tokens)

    monkeypatch.setattr(llm_mod, "chat", wrap)
    r = client.post("/api/alerts/ALT-H-20260910/investigate", params={"use_challenger": True})
    assert r.status_code == 200
    data = r.json()
    ctx = captured["ctx"]
    blob = json.dumps(ctx, ensure_ascii=False)
    assert "6222-H-7701" not in blob
    assert "江南连锁" not in blob
    assert "CLIENT_" in blob or ctx["customer"]["name"].startswith("CLIENT_")
    assert any(t["id"].startswith("TX-H-CASH") for t in ctx["transactions"])
    assert data["privacy"]["policy"] == "privacy_v2"
    assert data["privacy"]["egress_calls"] >= 1
    assert data["privacy"]["masked_names"] >= 1
    assert data["privacy"]["masked_accounts"] >= 1
    assert any(s.get("role") == "Privacy" for s in data["steps"])
