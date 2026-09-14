"""独立集健全性：唯一性、无标签泄漏、规则层同构、极性标注（不调模型）。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "experiments" / "benchmark"
SET_PATH = BENCH / "independent_set.json"
NOPOL_PATH = BENCH / "independent_set_nopolarity.json"
BLIND_PATH = BENCH / "blind_set.json"
STRUCT_PATH = BENCH / "struct_set.json"

sys.path.insert(0, str(BENCH))
from blind_families import JUDGE_V3_EXEMPLARS  # noqa: E402
from struct_families import STRUCT_FORBIDDEN_RULES  # noqa: E402

LEAK_TOKENS = ("叙事族", "关键线索", "干扰线索", "合成", "占位", "synthetic", "gold", "annotation_reason")

# 盲区集只约束「人写的输入」：规则层 / 知识库原文不受控。
BLIND_SCAN_KEYS = ("alert_type", "industry", "summary", "customer", "candidate_evidence", "transactions")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_unique_no_leak(payload: dict) -> None:
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
        assert "missing_evidence" not in vig
        for ev in vig["candidate_evidence"]:
            assert not str(ev["id"]).endswith("-S")
            assert not str(ev["id"]).endswith("-N")
            assert str(ev["id"]).startswith("IX-")


def test_independent_set_unique_and_no_leakage():
    _assert_unique_no_leak(_load(SET_PATH))


def test_independent_set_evidence_ids_are_product_compatible():
    for case in _load(SET_PATH)["cases"]:
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
    cases = _load(SET_PATH)["cases"]
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
        acc = vig["alert"]["account_id"]
        assert any(acc in (t["from_account"], t["to_account"]) for t in vig["transactions"])
    support_codes = {"structuring", "funnel", "night-out", "layering", "watchlist", "unregistered-counterparty"}
    for tag in ("atm_smurf", "invoice_circular", "crypto_onramp", "nested_shell_loan", "crowdfund_layering"):
        counts = codes_by_tag[tag]
        n_tag = sum(1 for c in cases if c["tag"] == tag)
        assert max((counts[c] for c in support_codes), default=0) >= n_tag * 0.9, (tag, counts)


def test_independent_set_no_missing_evidence_label_leak():
    payload = _load(SET_PATH)
    assert "不传 missing_evidence" in payload["judge_input_contract"]
    for case in payload["cases"]:
        vig = case["vignette"]
        assert "missing" not in json.dumps({k: v for k, v in vig.items() if k != "kb_hits"}, ensure_ascii=False).lower()


def test_nopolarity_set_notes_are_context_only():
    payload = _load(NOPOL_PATH)
    assert payload["variant"] == "nopolarity"
    _assert_unique_no_leak(payload)
    for case in payload["cases"]:
        notes = [f for f in case["vignette"]["findings"] if f["code"] == "case-note"]
        assert notes and all(f["polarity"] == "context" for f in notes), case["case_id"]
        # 规则层极性仍保留
        rules = [f for f in case["vignette"]["findings"] if f["code"] not in ("case-note", "alert-brief")]
        assert rules


def test_blind_set_avoids_judge_v3_exemplars():
    payload = _load(BLIND_PATH)
    assert payload["variant"] == "blind"
    _assert_unique_no_leak(payload)
    for case in payload["cases"]:
        vig = case["vignette"]
        scanned = {k: vig[k] for k in BLIND_SCAN_KEYS if k in vig}
        blob = json.dumps(scanned, ensure_ascii=False)
        for token in JUDGE_V3_EXEMPLARS:
            assert token not in blob, f"{case['case_id']} {case['tag']} 含例举词 {token}"
        for f in vig["findings"]:
            if f["code"] in ("case-note", "alert-brief"):
                for token in JUDGE_V3_EXEMPLARS:
                    assert token not in (f.get("detail") or ""), (case["case_id"], f["code"], token)
        for t in vig["transactions"]:
            for token in JUDGE_V3_EXEMPLARS:
                assert token not in (t.get("remark") or ""), (case["case_id"], t["remark"], token)
        assert "过桥" not in (vig["baseline"].get("peer_note") or "")
        assert "归集" not in (vig["baseline"].get("peer_note") or "")
        assert "阈值" not in (vig["baseline"].get("peer_note") or "")
        assert "存入" not in (vig["baseline"].get("peer_note") or "")


def _scan_blind_fields(vig: dict) -> str:
    scanned = {k: vig[k] for k in BLIND_SCAN_KEYS if k in vig}
    return json.dumps(scanned, ensure_ascii=False)


def test_blind_struct_set_avoids_exemplars_and_structural_rules():
    payload = _load(STRUCT_PATH)
    assert payload["variant"] == "blind_struct"
    _assert_unique_no_leak(payload)
    assert payload["n"] >= 200
    for case in payload["cases"]:
        vig = case["vignette"]
        blob = _scan_blind_fields(vig)
        for token in JUDGE_V3_EXEMPLARS:
            assert token not in blob, f"{case['case_id']} {case['tag']} 含例举词 {token}"
        for f in vig["findings"]:
            if f["code"] in ("case-note", "alert-brief"):
                for token in JUDGE_V3_EXEMPLARS:
                    assert token not in (f.get("detail") or ""), (case["case_id"], f["code"], token)
        for t in vig["transactions"]:
            for token in JUDGE_V3_EXEMPLARS:
                assert token not in (t.get("remark") or ""), (case["case_id"], t["remark"], token)
            hour = str(t.get("occurred_at") or "")[11:13]
            if t.get("from_account") == vig["alert"]["account_id"]:
                assert hour < "21" and hour >= "06", (case["case_id"], t["occurred_at"])
        note = vig["baseline"].get("peer_note") or ""
        for token in ("过桥", "归集", "阈值", "存入", "财政", "监管账户"):
            assert token not in note, (case["case_id"], note, token)
        codes = set(case["rule_finding_codes"])
        assert codes == {"alert-trigger"}, (case["case_id"], case["tag"], codes)
        for code in STRUCT_FORBIDDEN_RULES:
            assert code not in codes
        # 企业案不得达到 funnel 阈值
        if vig["customer"]["kind"] == "enterprise":
            acc = vig["alert"]["account_id"]
            in_accounts = {t["from_account"] for t in vig["transactions"] if t["to_account"] == acc}
            assert len(in_accounts) < 4, (case["case_id"], len(in_accounts))
