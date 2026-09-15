from fastapi import HTTPException
import pytest

from app.display import case_no, display_name, mask_account
from app.security import AuthUser
from app.workflow import assert_decision_allowed


def _login(client, staff_id="002183", password="aml123"):
    r = client.post("/api/auth/login", json={"staff_id": staff_id, "password": password})
    assert r.status_code == 200, r.text
    return {"X-Huicha-Session": r.json()["token"]}


def test_case_no_and_mask():
    assert case_no("ALT-B-20260910") == "20260910-B"
    assert mask_account("6222-A-8801") == "6222****8801"
    assert display_name("金辉商贸（演示）") == "金辉商贸"


def test_investigator_cannot_confirm():
    user = AuthUser(staff_id="002183", name="陈析", role="反洗钱调查员")
    with pytest.raises(HTTPException) as ei:
        assert_decision_allowed(user, "confirm", current_decision="", can_sign=True, note="")
    assert ei.value.status_code == 403


def test_reviewer_cannot_confirm_before_submit():
    user = AuthUser(staff_id="002201", name="李审", role="合规复核")
    with pytest.raises(HTTPException) as ei:
        assert_decision_allowed(user, "confirm", current_decision="", can_sign=True, note="")
    assert ei.value.status_code == 400


def test_submit_then_reviewer_confirm(client):
    inv_h = _login(client)
    rev_h = _login(client, "002201", "aml123")
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    blocked = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": ""},
        headers=inv_h,
    )
    assert blocked.status_code == 403
    submitted = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": ""},
        headers=inv_h,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_review"
    assert submitted.json()["human_decision"] == "submit"
    signed = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": "同意排除"},
        headers=rev_h,
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["human_decision"] == "confirm"
    assert body["signed_by_name"] == "李审"
    assert body["final_action"] == "human_only"
    detail = client.get("/api/alerts/ALT-A-20260910").json()
    assert detail["human_decision"] == "confirm"
    assert detail["signed_by_name"] == "李审"
    assert detail["submitted_by_name"] == "陈析"
    listed = client.get("/api/alerts").json()
    row = next(x for x in listed if x["id"] == "ALT-A-20260910")
    assert row["case_no"] == "20260910-A"
    assert "****" in row["account_masked"]


def test_self_review_blocked(client):
    rev_h = _login(client, "002201", "aml123")
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    # 复核岗不能提交
    r = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": ""},
        headers=rev_h,
    )
    assert r.status_code == 403
