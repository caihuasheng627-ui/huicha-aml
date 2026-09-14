"""独立集健全性：唯一性、无标签泄漏、规则层同构、极性标注（不调模型）。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SET_PATH = ROOT / "experiments" / "benchmark" / "independent_set.json"

LEAK_TOKENS = ("叙事族", "关键线索", "干扰线索", "合成", "占位", "synthetic", "gold", "annotation_reason")


def _load() -> dict:
    return json.loads(SET_PATH.read_text(encoding="utf-8"))


def test_independent_set_unique_and_no_leakage():
    payload = _load()
    cases = payload["cases"]
    assert len(cases) >= 200
    fps = {c["fingerprint"] for c in cases}
    assert len(fps) >= 200
    assert payload.get("n_unique", len(fps)) >= 200

    for case in cases:
        vig = case["vignette"]
        blob = json.dumps(vig, ensure_ascii=False)
        for token in LEAK_TOKENS:
            assert token not in blob, f"{case['case_id']} 输入含泄漏/占位字样: {token}"
        assert case["tag"] not in blob
        assert case["gold"] not in blob
        # v2 的 observe 泄漏源：missing_evidence 不得再作为 Judge 输入出现
        assert "missing_evidence" not in vig
        for ev in vig["candidate_evidence"]:
            assert not str(ev["id"]).endswith("-S")
            assert not str(ev["id"]).endswith("-N")
            assert str(ev["id"]).startswith("IX-")


def test_independent_set_evidence_ids_are_product_compatible():
    """产品 enrich_judge 会过滤 EV- 前缀；独立集必须只用 TX-/IX-/KB-/C-/ACC- 编号。"""
    for case in _load()["cases"]:
        vig = case["vignette"]
        for eid in vig["allowed_evidence"]:
            assert not str(eid).startswith("EV-"), eid
        tx_ids = {t["id"] for t in vig["transactions"]}
        assert tx_ids and all(x.startswith("TX-") for x in tx_ids)
        assert tx_ids <= set(vig["allowed_evidence"])
        for f in vig["findings"]:
            assert f["code"] and f["polarity"] in {"support", "counter", "context"}
            assert set(f["evidence_ids"]) <= set(vig["allowed_evidence"]), f
        for eid in case["gold_support_ids"] + case["gold_contradict_ids"]:
            assert eid in vig["allowed_evidence"]


def test_independent_set_rules_layer_and_polarity():
    """流水须让产品规则层真的触发：exclude 族有反极性开脱证据，上报族有规则层 support finding。"""
    cases = _load()["cases"]
    codes_by_tag: dict[str, Counter] = {}
    for case in cases:
        vig = case["vignette"]
        findings = vig["findings"]
        rule_codes = set(case["rule_finding_codes"])
        codes_by_tag.setdefault(case["tag"], Counter()).update(rule_codes)
        note_pol = {f["polarity"] for f in findings if f["code"] == "case-note"}
        if case["gold"] == "exclude":
            assert "counter" in note_pol, case["case_id"]
        if case["gold"] == "suggest_report":
            assert "support" in note_pol, case["case_id"]
        assert any(f["code"] not in ("case-note", "alert-brief") for f in findings), case["case_id"]
        # 交易结构必须与告警一致：中心账户出现在每条流水的一侧或形成过桥链
        acc = vig["alert"]["account_id"]
        assert any(acc in (t["from_account"], t["to_account"]) for t in vig["transactions"])
    # 上报族至少一个规则层 support 码在该族大多数样本中出现
    support_codes = {"structuring", "funnel", "night-out", "layering", "watchlist", "unregistered-counterparty"}
    for tag in ("atm_smurf", "invoice_circular", "crypto_onramp", "nested_shell_loan", "crowdfund_layering"):
        counts = codes_by_tag[tag]
        n_tag = sum(1 for c in cases if c["tag"] == tag)
        assert max((counts[c] for c in support_codes), default=0) >= n_tag * 0.9, (tag, counts)


def test_independent_set_no_missing_evidence_label_leak():
    """三档都不再带任何待补材料输入；gold 与输入中的“缺/待补”字样只允许来自叙事本身。"""
    payload = _load()
    assert "不传 missing_evidence" in payload["judge_input_contract"]
    for case in payload["cases"]:
        vig = case["vignette"]
        assert "missing" not in json.dumps({k: v for k, v in vig.items() if k != "kb_hits"}, ensure_ascii=False).lower()
