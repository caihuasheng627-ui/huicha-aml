"""调查处置分岗：调查员提交复核，复核岗签发。提交人不得复核本人案件。"""

from __future__ import annotations

from fastapi import HTTPException

from .security import AuthUser

ROLE_INVESTIGATOR = "反洗钱调查员"
ROLE_REVIEWER = "合规复核"

ALLOWED = {"submit", "confirm", "modify", "reject"}


def collect_sign_blockers(
    *,
    fact_issues: list | None = None,
    judge_validation: dict | None = None,
    use_challenger: bool = True,
    reliability: dict | None = None,
) -> list[dict]:
    blockers: list[dict] = []
    if fact_issues:
        blockers.append({"code": "fact_check", "message": "事实回查未通过"})
    for row in (reliability or {}).get("reasons") or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip() or "abstain"
        message = str(row.get("message") or "").strip() or "当前结论不可直接签发"
        if any(b["code"] == code for b in blockers):
            continue
        blockers.append({"code": code, "message": message})
    if use_challenger and judge_validation and not judge_validation.get("passed", True):
        if not any(b["code"] in {"citation_failed", "predicate_failed", "judge_fallback"} for b in blockers):
            blockers.append(
                {
                    "code": "judge_contract",
                    "message": judge_validation.get("reason") or "证据契约未通过",
                }
            )
    return blockers


def sign_block_reason(blockers: list[dict] | None, *, default: str = "事实回查未通过") -> str:
    messages = []
    for row in blockers or []:
        text = str((row or {}).get("message") or "").strip()
        if text and text not in messages:
            messages.append(text)
    return "；".join(messages) if messages else default


def assert_decision_allowed(
    user: AuthUser,
    decision: str,
    *,
    current_decision: str,
    can_sign: bool,
    note: str,
    submitted_by_id: str = "",
    sign_blockers: list | None = None,
) -> None:
    if decision not in ALLOWED:
        raise HTTPException(400, "decision 必须是 submit / confirm / modify / reject")

    finalized = current_decision in {"confirm", "modify"}
    if finalized and decision != "reject":
        raise HTTPException(400, "本案已签发，不能重复处置")

    block_text = sign_block_reason(sign_blockers)

    if user.role == ROLE_INVESTIGATOR:
        if decision not in {"submit", "reject"}:
            raise HTTPException(403, "调查员只能提交复核或退回重查，签发须由复核岗完成")
        if decision == "submit":
            if not can_sign and not (note or "").strip():
                raise HTTPException(400, f"{block_text}时，提交复核须填写说明")
        return

    if user.role == ROLE_REVIEWER:
        if decision == "submit":
            raise HTTPException(403, "复核岗不能代为提交，请由调查员提交复核")
        if current_decision != "submit" and decision in {"confirm", "modify"}:
            raise HTTPException(400, "须先由调查员提交复核")
        if submitted_by_id and submitted_by_id == user.staff_id:
            raise HTTPException(403, "提交人不得复核本人案件")
        if decision == "confirm" and not can_sign:
            raise HTTPException(400, f"{block_text}，不能签发")
        if decision == "modify" and not can_sign and not (note or "").strip():
            raise HTTPException(400, f"{block_text}时，「修改后签发」须填写修改说明")
        return

    raise HTTPException(403, "当前岗位无权处置本案")
