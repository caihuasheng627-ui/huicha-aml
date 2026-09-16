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


def test_submit_does_not_write_signed_by(client):
    inv_h = _login(client)
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    submitted = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": ""},
        headers=inv_h,
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["human_decision"] == "submit"
    assert body["signed_by_id"] == ""
    assert body["signed_by_name"] == ""
    detail = client.get("/api/alerts/ALT-A-20260910").json()
    assert detail["human_decision"] == "submit"
    assert detail["submitted_by_name"] == "陈析"
    assert not detail["signed_by_id"]
    assert not detail["signed_by_name"]
    text = client.get("/api/alerts/ALT-A-20260910/export", headers=inv_h).text
    assert "陈析" in text
    assert "（未签发）" in text


def test_reinvestigate_resets_pending_review(client):
    inv_h = _login(client)
    rev_h = _login(client, "002201", "aml123")
    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    submitted = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": ""},
        headers=inv_h,
    )
    assert submitted.json()["status"] == "pending_review"
    again = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    assert again.status_code == 200, again.text
    listed = client.get("/api/alerts").json()
    row = next(x for x in listed if x["id"] == "ALT-A-20260910")
    assert row["status"] == "investigating"
    assert row["status"] != "pending_review"
    assert not row.get("human_decision")
    detail = client.get("/api/alerts/ALT-A-20260910").json()
    assert detail["alert"]["status"] == "investigating"
    assert not detail["human_decision"]
    assert not detail["signed_by_id"]
    assert not (detail.get("investigation") or {}).get("human_review", {}).get("submitted_by_id")
    blocked = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": "同意排除"},
        headers=rev_h,
    )
    assert blocked.status_code == 400
    assert "提交复核" in blocked.json()["detail"]
    submitted2 = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": ""},
        headers=inv_h,
    )
    assert submitted2.status_code == 200, submitted2.text
    signed = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": "同意排除"},
        headers=rev_h,
    )
    assert signed.status_code == 200, signed.text


def test_reinvestigate_resets_monitoring(client):
    from tests.conftest import dual_confirm

    client.post("/api/alerts/ALT-F-20260910/investigate", params={"use_challenger": True})
    ok, _ = dual_confirm(client, "ALT-F-20260910")
    assert ok.status_code == 200
    assert ok.json()["status"] == "monitoring"
    again = client.post("/api/alerts/ALT-F-20260910/investigate", params={"use_challenger": True})
    assert again.status_code == 200, again.text
    listed = client.get("/api/alerts").json()
    row = next(x for x in listed if x["id"] == "ALT-F-20260910")
    assert row["status"] == "investigating"
    assert not row.get("human_decision")
    detail = client.get("/api/alerts/ALT-F-20260910").json()
    assert detail["alert"]["status"] == "investigating"
    assert not detail["human_decision"]
    assert not detail["signed_by_name"]


def test_investigation_mutex_second_request_409(client):
    from fastapi import HTTPException

    from app.main import _end_investigation, _try_begin_investigation

    aid = "ALT-A-20260910"
    _end_investigation(aid)
    _try_begin_investigation(aid)
    try:
        with pytest.raises(HTTPException) as ei:
            _try_begin_investigation(aid)
        assert ei.value.status_code == 409
        assert ei.value.detail == "本案正在调查"
        post = client.post(f"/api/alerts/{aid}/investigate", params={"use_challenger": True})
        assert post.status_code == 409
        assert post.json()["detail"] == "本案正在调查"
        streamed = client.get(f"/api/alerts/{aid}/investigate/stream", params={"use_challenger": True})
        assert streamed.status_code == 409
        assert streamed.json()["detail"] == "本案正在调查"
    finally:
        _end_investigation(aid)
    ok = client.post(f"/api/alerts/{aid}/investigate", params={"use_challenger": True})
    assert ok.status_code == 200, ok.text
