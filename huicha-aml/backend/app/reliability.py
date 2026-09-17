"""AI 可靠性与弃权：不改三档结论，只决定能否直接签发。"""

from __future__ import annotations

from .schema import AgentReliability, AbstainReason

LOW_CONFIDENCE = 0.55
HARD_CITATION = {
    "uncited_rationale",
    "invalid_citation",
    "missing_support",
    "empty_rationale",
    "missing_rationale",
    "judge_failure",
    "invalid_output",
}
HARD_PREDICATE = {"predicate_failed"}


def _reason(code: str, severity: str, message: str) -> dict:
    return AbstainReason(code=code, severity=severity, message=message).model_dump()


def compute_reliability(
    *,
    use_challenger: bool,
    judge: dict | None = None,
    judge_validation: dict | None = None,
    fallback_reason: str = "",
    baseline: dict | None = None,
    counterfactual: dict | None = None,
    evidence_sufficiency: dict | None = None,
) -> dict:
    if not use_challenger:
        return AgentReliability(
            stance="committed",
            note="慧查agent 关闭，仅规则对照，不产生弃权。",
        ).model_dump()

    judge = judge or {}
    validation = judge_validation or {}
    baseline = baseline or {}
    counterfactual = counterfactual or {}
    sufficiency = evidence_sufficiency or {}
    reasons: list[dict] = []
    issues = validation.get("issues") or []
    kinds = {str(item.get("kind") or "") for item in issues if isinstance(item, dict)}

    if fallback_reason or validation.get("score_kind") == "fallback":
        reasons.append(_reason("judge_fallback", "hard", "慧查agent 已降级为规则对照，不能直接签发"))
    elif not validation.get("passed", True):
        if kinds & HARD_PREDICATE:
            reasons.append(_reason("predicate_failed", "hard", "可执行谓词未通过核验，不能直接签发"))
        if kinds & HARD_CITATION or not (kinds & HARD_PREDICATE):
            reasons.append(_reason("citation_failed", "hard", "证据契约未通过，不能直接签发"))

    if counterfactual.get("performed") and counterfactual.get("validated") is False:
        reasons.append(_reason("cf_invalid", "hard", "反事实轮次输出无效，不能判断证据依赖"))

    try:
        confidence = float(judge.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    rule_conc = baseline.get("conclusion") or ""
    judge_conc = judge.get("disposition") or ""
    if rule_conc and judge_conc and rule_conc != judge_conc and confidence < LOW_CONFIDENCE:
        reasons.append(
            _reason(
                "rule_judge_conflict_low_conf",
                "soft",
                "规则对照与 AI 建议分歧且自评把握度偏低，系统弃权",
            )
        )

    necessary = sufficiency.get("necessary_ids") or []
    if (
        judge_conc == "suggest_report"
        and counterfactual.get("performed")
        and counterfactual.get("validated")
        and not necessary
    ):
        reasons.append(_reason("cf_not_dependent", "soft", "建议上报未形成对其声明证据的依赖，系统弃权"))

    if sufficiency and sufficiency.get("verified") is False and not necessary:
        reasons.append(_reason("evidence_core_unverified", "soft", "有界证据搜索未形成稳定核心，系统弃权"))

    seen: set[str] = set()
    unique: list[dict] = []
    for row in reasons:
        if row["code"] in seen:
            continue
        seen.add(row["code"])
        unique.append(row)
    stance = "abstain" if unique else "committed"
    if stance == "abstain":
        note = "系统弃权：保留 AI 倾向档，但不可直接签发。"
    else:
        note = "已形成可签发倾向：谓词与证据核心通过核验。"
    return AgentReliability(stance=stance, reasons=unique, note=note).model_dump()
