"""Challenger 消融框架。

比较：
  A. Rule Only
  B. Rule + Analyst
  C. Rule + Analyst + Challenger
  D. Rule + Analyst + Evidence Validator
  E. Full System

能力指标未在独立集上评估时输出 Not evaluated yet。
机制验证请运行：cd backend && python -m app.experiments

过程对照（agent 管线 vs 直连 `rule_baseline`/`enrich_judge`，不是 F1）：
  pytest：backend/tests/test_path_compare.py
  脚本：python experiments/compare_agent_direct.py
  真实调用：加 --real 或 HUICHA_COMPARE_REAL=1；仍为合成告警，禁止写成生产准确率。
"""

from __future__ import annotations

import json

VARIANTS = [
    "A_rule_only",
    "B_rule_analyst",
    "C_rule_analyst_challenger",
    "D_rule_analyst_validator",
    "E_full_system",
]

METRICS = [
    "risk_accuracy",
    "false_positive_rate",
    "evidence_validity",
    "hallucination_rate",
]


def main() -> dict:
    rows = {v: {m: "Not evaluated yet" for m in METRICS} for v in VARIANTS}
    out = {
        "status": "TODO",
        "data_note": "synthetic",
        "variants": rows,
        "note": "请用独立标注集填写；不要把模板精标重合率当成准确率。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
