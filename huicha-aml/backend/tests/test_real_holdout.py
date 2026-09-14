"""真实 hold-out 导入：字段校验与去标识。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "experiments" / "benchmark"
sys.path.insert(0, str(BENCH))

from import_real_cases import PLACEHOLDER_CSV, build_payload, cases_from_csv, mask_text, row_to_case  # noqa: E402


def test_placeholder_set_is_masked_and_not_for_results():
    payload = json.loads((BENCH / "real_holdout.json").read_text(encoding="utf-8"))
    assert payload["data_note"] == "placeholder"
    assert payload["n"] == 5
    blob = json.dumps(payload, ensure_ascii=False)
    assert "110101199001011234" not in blob
    assert "13800138000" not in blob
    for case in payload["cases"]:
        name = case["vignette"]["customer"]["name"]
        if case["vignette"]["customer"]["kind"] == "individual":
            assert name.endswith("**")
            assert len(name) == 3


def test_rejects_bad_gold():
    csv = "gold,alert_type,industry,customer_kind,summary\nbad,大额,制造业,individual,摘要\n"
    with pytest.raises(ValueError, match="gold"):
        cases_from_csv(csv)


def test_masks_id_and_phone():
    text = mask_text("客户身份证 110101199001011234 手机 13800138000")
    assert "[ID]" in text and "110101199001011234" not in text
    assert "[PHONE]" in text and "13800138000" not in text
    row = {
        "gold": "observe",
        "alert_type": "大额转账待核",
        "industry": "个人-受雇",
        "customer_kind": "individual",
        "customer_name": "张三丰",
        "summary": "客户身份证 110101199001011234 转出",
        "evidence": "手机 13912345678 来电说明",
        "account_id": "6222000000000000",
    }
    case = row_to_case(row, 1)
    blob = json.dumps(case, ensure_ascii=False)
    assert "110101199001011234" not in blob
    assert "13912345678" not in blob
    assert "6222000000000000" not in blob
    assert case["vignette"]["customer"]["name"] == "张**"


def test_build_payload_rejects_residual_pii():
    cases = cases_from_csv(PLACEHOLDER_CSV)
    cases[0]["vignette"]["summary"] += " 110101199001011234"
    with pytest.raises(RuntimeError, match="身份证"):
        build_payload(cases, data_note="placeholder", source="real_holdout_placeholder")


OUTCOME_LEAK = (
    "有期徒刑",
    "判处",
    "判决书",
    "洗钱罪",
    "帮信罪",
    "掩饰、隐瞒",
    "公诉",
    "移送起诉",
    "罚金",
    "已报送",
    "重点可疑交易报告",
)


def test_public_rewrite_set_is_report_probe_not_results():
    payload = json.loads((BENCH / "public_rewrite.json").read_text(encoding="utf-8"))
    assert payload["data_note"] == "public-rewrite"
    assert payload["n"] == 12
    assert payload["n_unique"] == 12
    assert payload["gold_distribution"] == {"suggest_report": 12}
    assert payload["citations"]
    blob = json.dumps(payload, ensure_ascii=False)
    assert "110101199001011234" not in blob
    assert "13800138000" not in blob
    golds = {c["gold"] for c in payload["cases"]}
    assert golds == {"suggest_report"}
    urls = {c["source_citation"]["url"] for c in payload["cases"]}
    assert all(u.startswith("http") for u in urls)
    assert len(urls) >= 8
    for case in payload["cases"]:
        assert case["gold_provenance"] == "author-mapped-from-public-conclusion"
        vig = json.dumps(case["vignette"], ensure_ascii=False)
        for token in OUTCOME_LEAK:
            assert token not in vig, f"{case['case_id']} vignette 含结局泄漏: {token}"
        name = case["vignette"]["customer"]["name"]
        if case["vignette"]["customer"]["kind"] == "individual":
            assert name.endswith("**")
        txs = case["vignette"]["transactions"]
        assert len(txs) >= 6
        assert all(t["id"].startswith("TX-") for t in txs)


def test_public_rewrite_rebuild_is_stable():
    from public_rewrite_cases import public_rewrite_rows  # noqa: E402

    existing = json.loads((BENCH / "public_rewrite.json").read_text(encoding="utf-8"))
    rebuilt = [row_to_case(row, i) for i, row in enumerate(public_rewrite_rows(), 1)]
    assert [c["fingerprint"] for c in rebuilt] == [c["fingerprint"] for c in existing["cases"]]


def test_skip_results_write_covers_public_rewrite():
    from import_real_cases import skip_results_write  # noqa: E402

    assert skip_results_write({"data_note": "public-rewrite", "source": "public_rewrite_holdout"})
    assert skip_results_write({"data_note": "placeholder", "source": "real_holdout_placeholder"})
    assert not skip_results_write(
        {"data_note": "synthetic-blind-struct-v1", "source": "narrative_vignette_blind_struct"}
    )
