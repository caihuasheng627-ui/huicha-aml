"""Evidence Validator：无证据 / 跨案 / 越界 delta 的 Claim 不得进分。"""

from __future__ import annotations

DELTA_BOUND = 0.15


def validate_claim(
    *,
    claim: str,
    evidence_ids: list[str],
    delta: float,
    allowed: set[str],
    case_id: str = "",
    evidence_case: dict[str, str] | None = None,
) -> dict:
    """evidence_case: evidence_id -> case_id，用于跨案拒绝。"""
    ids = [str(x).strip() for x in (evidence_ids or []) if str(x).strip()]
    if abs(float(delta)) > DELTA_BOUND + 1e-9:
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "reason": f"delta {delta} 超出 ±{DELTA_BOUND}，已拒绝",
            "rejected_delta": delta,
        }
    if not ids and float(delta) != 0:
        return {
            "valid": False,
            "evidence_ids": [],
            "support_score": 0.0,
            "reason": "调分 Claim 缺少 evidence_ids",
            "rejected_delta": delta,
        }
    if case_id and evidence_case:
        cross = [i for i in ids if evidence_case.get(i) and evidence_case[i] != case_id]
        if cross:
            return {
                "valid": False,
                "evidence_ids": ids,
                "support_score": 0.0,
                "reason": f"跨案件证据：{','.join(cross[:6])}",
                "rejected_delta": delta,
            }
    missing = [i for i in ids if i not in allowed]
    if missing:
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "reason": f"证据不存在或不属于本轮工具结果：{','.join(missing[:6])}",
            "rejected_delta": delta,
        }
    if not (claim or "").strip():
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "reason": "空 claim",
            "rejected_delta": delta,
        }
    return {
        "valid": True,
        "evidence_ids": ids,
        "support_score": 1.0 if ids else 0.0,
        "score_kind": "id_membership",
        "reason": "证据编号属于本案件工具结果（不是语义支持度或校准置信度）",
        "rejected_delta": None,
    }


def filter_challenger_items(
    items: list[dict],
    *,
    allowed: set[str],
    case_id: str = "",
    evidence_case: dict[str, str] | None = None,
) -> tuple[list[dict], float, list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    total = 0.0
    for it in items:
        delta = float(it.get("delta") or 0)
        ev = it.get("evidence_ids") or []
        res = validate_claim(
            claim=str(it.get("claim") or it.get("title") or ""),
            evidence_ids=ev,
            delta=delta,
            allowed=allowed,
            case_id=case_id,
            evidence_case=evidence_case,
        )
        row = {**it, "validation": res}
        if not res["valid"]:
            row["delta"] = 0.0
            rejected.append(row)
            continue
        kept.append(row)
        total += delta
    total = max(-DELTA_BOUND, min(DELTA_BOUND, total))
    return kept, round(total, 4), rejected
