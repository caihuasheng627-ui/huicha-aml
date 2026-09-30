"""幻觉实验框架。

攻击集：
  1. 虚构交易 2. 虚构客户 3. 虚构账户 4. 虚构关系
  5. 虚构法规 6. 无证据风险结论 7. 夸大风险 8. 错误关联

比较：LLM / LLM+RAG / LLM+Evidence Validator / Full System
指标：Hallucination Rate / Detection Rate / Blocking Rate

没有真实结果之前不写百分比。
"""

from __future__ import annotations

import json
from pathlib import Path

ATTACKS = [
    "fake_transaction",
    "fake_customer",
    "fake_account",
    "fake_relationship",
    "fake_regulation",
    "risk_without_evidence",
    "inflated_risk",
    "wrong_link",
]

SYSTEMS = ["llm", "llm_rag", "llm_validator", "full_system"]


def _vs_attacks() -> dict | None:
    path = Path(__file__).resolve().parent / "RESULTS.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    block = data.get("vs_generic")
    if not isinstance(block, dict) or not isinstance(block.get("attacks"), dict):
        return None
    return block["attacks"]


def main() -> dict:
    out = {
        "status": "TODO",
        "attacks": ATTACKS,
        "systems": {
            s: {
                "hallucination_rate": "Not evaluated yet",
                "detection_rate": "Not evaluated yet",
                "blocking_rate": "Not evaluated yet",
            }
            for s in SYSTEMS
        },
        "note": "仓库内 inject_hallucination 只演示 6222-FAKE-9999 被事实回查拦截，不是完整攻击集评测。",
    }
    attacks = _vs_attacks()
    if attacks:
        fabricate = attacks.get("fabricate_bait") or {}
        fake_reg = attacks.get("fake_regulation") or {}
        a1 = fabricate.get("A1") if isinstance(fabricate.get("A1"), dict) else None
        a3 = fabricate.get("A3") if isinstance(fabricate.get("A3"), dict) else None
        reg_a1 = fake_reg.get("A1") if isinstance(fake_reg.get("A1"), dict) else None
        if a1 and a1.get("bait_cite_rate") is not None:
            out["systems"]["llm"]["hallucination_rate"] = a1["bait_cite_rate"]
        if reg_a1 and reg_a1.get("regulation_match_rate") is not None:
            out["systems"]["llm_rag"]["detection_rate"] = reg_a1["regulation_match_rate"]
        if a3 and a3.get("blocked_rate") is not None:
            out["systems"]["full_system"]["blocking_rate"] = a3["blocked_rate"]
            out["systems"]["full_system"]["hallucination_rate"] = a3.get("bait_cite_rate", "Not evaluated yet")
        out["status"] = "from_vs_generic"
        out["note"] = "上列数字只转写 RESULTS.json 的 vs_generic.attacks。没有对应跑次的格子仍是 Not evaluated yet。"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
