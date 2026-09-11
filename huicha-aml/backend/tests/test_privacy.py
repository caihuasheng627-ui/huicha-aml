from app.logging_util import redact
from app.privacy import PrivacyMap


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


def test_logs_redact_account_like_tokens():
    assert "6222-A-8801" not in redact("调查 6222-A-8801")
    assert "[REDACTED]" in redact("调查 6222-A-8801")
