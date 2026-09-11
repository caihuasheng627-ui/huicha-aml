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
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
