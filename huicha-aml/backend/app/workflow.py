"""调查处置分岗：调查员提交复核，复核岗签发。提交人不得复核本人案件。"""

from __future__ import annotations

from fastapi import HTTPException

from .security import AuthUser

ROLE_INVESTIGATOR = "反洗钱调查员"
ROLE_REVIEWER = "合规复核"

ALLOWED = {"submit", "confirm", "modify", "reject"}


def assert_decision_allowed(
    user: AuthUser,
    decision: str,
    *,
    current_decision: str,
    can_sign: bool,
    note: str,
    submitted_by_id: str = "",
) -> None:
    if decision not in ALLOWED:
        raise HTTPException(400, "decision 必须是 submit / confirm / modify / reject")

    finalized = current_decision in {"confirm", "modify"}
    if finalized and decision != "reject":
        raise HTTPException(400, "本案已签发，不能重复处置")

    if user.role == ROLE_INVESTIGATOR:
        if decision not in {"submit", "reject"}:
            raise HTTPException(403, "调查员只能提交复核或退回重查，签发须由复核岗完成")
        if decision == "submit":
            if not can_sign and not (note or "").strip():
                raise HTTPException(400, "事实回查未通过时，提交复核须填写说明")
        return

    if user.role == ROLE_REVIEWER:
        if decision == "submit":
            raise HTTPException(403, "复核岗不能代为提交，请由调查员提交复核")
        if current_decision != "submit" and decision in {"confirm", "modify"}:
            raise HTTPException(400, "须先由调查员提交复核")
        if submitted_by_id and submitted_by_id == user.staff_id:
            raise HTTPException(403, "提交人不得复核本人案件")
        if decision == "confirm" and not can_sign:
            raise HTTPException(400, "事实回查未通过，不能签发")
        if decision == "modify" and not can_sign and not (note or "").strip():
            raise HTTPException(400, "事实回查未通过时，「修改后签发」须填写修改说明")
        return

    raise HTTPException(403, "当前岗位无权处置本案")
