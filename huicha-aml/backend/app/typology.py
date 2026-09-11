"""AML 调查标签。不是交易级 suspicious/normal 二分类。"""

from __future__ import annotations

FINDING_TO_TAG = {
    "upstream-alert": "high_velocity",
    "structuring": "structuring",
    "funnel": "suspicious_network",
    "watchlist": "suspicious_network",
    "night-out": "rapid_transfer",
    "layering": "layering",
    "unregistered-counterparty": "mule_account",
    "pattern-peer": "other",
    "thin": "other",
}

COUNTER_TAGS = {
    "pattern-peer": "经营/同业基线抗辩",
    "thin": "模式不充分",
}


def tags_from_findings(findings: list[dict]) -> list[str]:
    out: list[str] = []
    for f in findings:
        tag = FINDING_TO_TAG.get(f.get("code") or "", "other")
        if tag not in out:
            out.append(tag)
    return out or ["other"]
