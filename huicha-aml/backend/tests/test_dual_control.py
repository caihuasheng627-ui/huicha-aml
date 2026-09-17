from fastapi import HTTPException
import pytest

from app.display import case_no, display_name, mask_account
from app.predicates import attach_stub_judge_predicate
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


def test_abstain_case_submit_confirm_modify_reject(client, monkeypatch):
    def fake_enrich(**kwargs):
        prior = kwargs.get("prior_issues") or []
        if any(isinstance(p, dict) and p.get("kind") == "counterfactual" for p in prior):
            allowed = kwargs.get("allowed_evidence") or []
            eid = next((e for e in allowed if str(e).startswith("TX-")), allowed[0] if allowed else "TX-A-IN-01")
            row = attach_stub_judge_predicate({"text": "移除关键证据后改观察", "evidence_ids": [eid]}, kwargs)
            return (
                {
                    "disposition": "observe",
                    "confidence": 0.4,
                    "typologies": [],
                    "supporting_evidence_ids": [eid],
                    "contradicting_evidence_ids": [],
                    "missing_evidence": [],
                    "rationale": [row],
                    "next_actions": [],
                },
                {},
            )
        row = attach_stub_judge_predicate({"text": "倾向上报", "evidence_ids": ["TX-A-IN-01"]}, kwargs)
        return (
            {
                "disposition": "suggest_report",
                "confidence": 0.4,
                "typologies": ["structuring"],
                "supporting_evidence_ids": ["TX-A-IN-01"],
                "contradicting_evidence_ids": [],
                "missing_evidence": ["资金来源说明"],
                "rationale": [row],
                "next_actions": [],
            },
            {},
        )

    monkeypatch.setattr("app.agents.enrich_judge", fake_enrich)
    inv_h = _login(client)
    rev_h = _login(client, "002201", "aml123")
    data = client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True}).json()
    assert data["can_sign"] is False
    assert data["agent_reliability"]["stance"] == "abstain"
    blocked_submit = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": ""},
        headers=inv_h,
    )
    assert blocked_submit.status_code == 400
    submitted = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": "已人工复核弃权原因"},
        headers=inv_h,
    )
    assert submitted.status_code == 200, submitted.text
    blocked_confirm = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "confirm", "note": ""},
        headers=rev_h,
    )
    assert blocked_confirm.status_code == 400
    blocked_modify = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "modify", "note": ""},
        headers=rev_h,
    )
    assert blocked_modify.status_code == 400
    modified = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "modify", "note": "复核后改写结论并签发"},
        headers=rev_h,
    )
    assert modified.status_code == 200, modified.text

    client.post("/api/alerts/ALT-A-20260910/investigate", params={"use_challenger": True})
    submitted2 = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "submit", "note": "再次提交"},
        headers=inv_h,
    )
    assert submitted2.status_code == 200, submitted2.text
    rejected = client.post(
        "/api/alerts/ALT-A-20260910/decide",
        json={"decision": "reject", "note": "退回重查"},
        headers=rev_h,
    )
    assert rejected.status_code == 200, rejected.text


def test_blocked_sign_can_write_note_without_deciding(client):
    inv_h = _login(client)
    no_draft = client.post(
        "/api/alerts/ALT-A-20260910/note",
        json={"note": "先记一笔"},
        headers=inv_h,
    )
    assert no_draft.status_code == 400

    data = client.post(
        "/api/alerts/ALT-A-20260910/investigate",
        params={"use_challenger": True, "inject_hallucination": True},
    ).json()
    assert data["can_sign"] is False

    unauth = client.post("/api/alerts/ALT-A-20260910/note", json={"note": "未登录"})
    assert unauth.status_code == 401

    empty = client.post(
        "/api/alerts/ALT-A-20260910/note",
        json={"note": "  "},
        headers=inv_h,
    )
    assert empty.status_code == 400

    saved = client.post(
        "/api/alerts/ALT-A-20260910/note",
        json={"note": "幻觉账号已人工核对，维持观察待补证"},
        headers=inv_h,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["final_action"] == "draft_only"
    assert body["human_decision"] == ""
    assert body["can_sign"] is False
    assert "未改变签发状态" in body["note"]

    detail = client.get("/api/alerts/ALT-A-20260910").json()
    assert detail["human_decision"] in {"", None}
    assert detail["human_note"] == "幻觉账号已人工核对，维持观察待补证"
    assert detail["alert"]["status"] not in {"ready_to_file", "closed", "modified"}
    report = (detail.get("investigation") or {}).get("report") or {}
    assert "【补证备注】幻觉账号已人工核对，维持观察待补证" in (report.get("full_text") or "")
    assert (detail.get("investigation") or {}).get("human_review", {}).get("note") == "幻觉账号已人工核对，维持观察待补证"
