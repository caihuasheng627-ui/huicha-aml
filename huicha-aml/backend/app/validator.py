"""Evidence Validator：无证据 / 跨案 / 越界 delta / 谓词不成立的 Claim 不得进分。"""

from __future__ import annotations

from .predicates import _as_str_list, execute_predicate

DELTA_BOUND = 0.15


def validate_claim(
    *,
    claim: str,
    evidence_ids: list[str],
    delta: float,
    allowed: set[str],
    case_id: str = "",
    evidence_case: dict[str, str] | None = None,
    predicate: str = "",
    args: dict | None = None,
    facts: dict | None = None,
) -> dict:
    """调分 Claim 必须带封闭谓词，并由 facts 快照重新执行。"""
    ids = [str(x).strip() for x in (evidence_ids or []) if str(x).strip()]
    pred = str(predicate or "").strip()
    payload = args if isinstance(args, dict) else {}
    arg_ids = _as_str_list(payload.get("tx_ids"))
    for eid in arg_ids:
        if eid not in ids:
            ids.append(eid)

    if abs(float(delta)) > DELTA_BOUND + 1e-9:
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "score_kind": "rejected",
            "predicate": pred,
            "reason": f"delta {delta} 超出 ±{DELTA_BOUND}，已拒绝",
            "rejected_delta": delta,
        }
    if not ids and float(delta) != 0:
        return {
            "valid": False,
            "evidence_ids": [],
            "support_score": 0.0,
            "score_kind": "rejected",
            "predicate": pred,
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
                "score_kind": "rejected",
                "predicate": pred,
                "reason": f"跨案件证据：{','.join(cross[:6])}",
                "rejected_delta": delta,
            }
    missing = [i for i in ids if i not in allowed]
    if missing:
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "score_kind": "rejected",
            "predicate": pred,
            "reason": f"证据不存在或不属于本轮工具结果：{','.join(missing[:6])}",
            "rejected_delta": delta,
        }
    if not (claim or "").strip():
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "score_kind": "rejected",
            "predicate": pred,
            "reason": "空 claim",
            "rejected_delta": delta,
        }

    if not pred:
        if float(delta) != 0:
            return {
                "valid": False,
                "evidence_ids": ids,
                "support_score": 0.0,
                "score_kind": "rejected",
                "predicate": "",
                "reason": "调分 Claim 缺少可执行谓词",
                "rejected_delta": delta,
            }
        return {
            "valid": True,
            "evidence_ids": ids,
            "support_score": 1.0 if ids else 0.0,
            "score_kind": "id_membership",
            "predicate": "",
            "reason": "中性说明（delta=0）未执行谓词；编号属于本案工具结果",
            "rejected_delta": None,
        }

    executed = execute_predicate(pred, payload, facts)
    observed = executed.get("observed") or {}
    if not executed.get("ok"):
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "score_kind": "rejected",
            "predicate": pred,
            "observed": observed,
            "reason": executed.get("reason") or "谓词无法执行",
            "rejected_delta": delta,
        }
    if not executed.get("true"):
        return {
            "valid": False,
            "evidence_ids": ids,
            "support_score": 0.0,
            "score_kind": "predicate_failed",
            "predicate": pred,
            "observed": observed,
            "reason": f"谓词 {pred} 经数据核验不成立：{executed.get('reason') or ''}".strip(),
            "rejected_delta": delta,
        }
    return {
        "valid": True,
        "evidence_ids": ids,
        "support_score": 1.0,
        "score_kind": "predicate_verified",
        "predicate": pred,
        "observed": observed,
        "reason": f"谓词 {pred} 在本案数据上成立（不是语义支持度或校准置信度）",
        "rejected_delta": None,
    }


def filter_challenger_items(
    items: list[dict],
    *,
    allowed: set[str],
    case_id: str = "",
    evidence_case: dict[str, str] | None = None,
    facts: dict | None = None,
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
            predicate=str(it.get("predicate") or ""),
            args=it.get("args") if isinstance(it.get("args"), dict) else {},
            facts=facts,
        )
        row = {**it, "evidence_ids": res.get("evidence_ids") or ev, "validation": res}
        if not res["valid"]:
            row["delta"] = 0.0
            rejected.append(row)
            continue
        kept.append(row)
        total += delta
    total = max(-DELTA_BOUND, min(DELTA_BOUND, total))
    return kept, round(total, 4), rejected
