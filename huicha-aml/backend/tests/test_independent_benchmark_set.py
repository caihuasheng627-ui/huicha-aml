"""独立集健全性：唯一性与无标签泄漏（不调模型）。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SET_PATH = ROOT / "experiments" / "benchmark" / "independent_set.json"


def test_independent_set_unique_and_no_leakage():
    payload = json.loads(SET_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) >= 200
    fps = {c["fingerprint"] for c in cases}
    assert len(fps) >= 200
    assert payload.get("n_unique", len(fps)) >= 200

    for case in cases:
        vig = case["vignette"]
        blob = json.dumps(vig, ensure_ascii=False)
        assert "叙事族" not in blob
        assert "关键线索" not in blob
        assert "干扰线索" not in blob
        assert case["tag"] not in (vig.get("summary") or "")
        assert "annotation_reason" not in vig
        for ev in vig["candidate_evidence"]:
            assert not str(ev["id"]).endswith("-S")
            assert not str(ev["id"]).endswith("-N")
        # gold 不含空信息 KYC 摘要
        for eid in case.get("gold_support_ids") or []:
            text = next((e["text"] for e in vig["candidate_evidence"] if e["id"] == eid), "")
            assert "合成 vignette" not in text
