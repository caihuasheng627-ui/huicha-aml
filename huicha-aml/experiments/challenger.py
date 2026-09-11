"""Challenger 专项：有界 delta、无证据拒绝。机制验证见 backend `python -m app.experiments`。"""

from __future__ import annotations

import json

def main() -> dict:
    out = {
        "status": "framework_only",
        "delta_bound": 0.15,
        "reject_if": ["abs(delta)>0.15", "missing evidence", "unknown id", "cross-case"],
        "risk_accuracy": "Not evaluated yet",
        "false_positive_rate": "Not evaluated yet",
        "note": "单测覆盖 Reject 规则；能力指标待独立集。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
