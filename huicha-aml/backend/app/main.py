import json
import queue
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .agents import run_investigation
from .checklist import (
    apply_remarks_to_report,
    attach_checklist,
    enrich_counterparties,
    generate_checklist,
    merge_note,
    scrub_payload_checklist,
)
from .notes import (
    FINALIZED,
    NOTE_MAX_LEN,
    check_note_facts,
    compose_human_note,
    note_metrics,
    sanitize_note,
    snapshot_blockers,
)
from .database import Base, SessionLocal, engine, get_db, migrate_sqlite
from .display import case_no, mask_account
from .knowledge import corpus_size, get_knowledge, list_knowledge, retrieval_mode, search_knowledge, search_unit_count
from .llm import investigation_tokens, llm_mode, llm_model
from .models import Alert, AmlCase, AuditLog, Customer, Investigation, utcnow
from .case_store import persist_human_decision, seed_prompt_versions
from .security import (
    auth_mode,
    cors_origins,
    create_session,
    demo_token,
    destroy_session,
    list_demo_accounts,
    require_user,
    resolve_session,
)
from .workflow import assert_decision_allowed
from .privacy import POLICY_VERSION, PrivacyLeakError
from .seed import seed_if_empty

DECIDE_LABEL = {
    "submit": "已提交复核",
    "confirm": "已记录签发",
    "modify": "修改后采纳",
    "reject": "已驳回",
}

CN_TZ = timezone(timedelta(hours=8))


def format_cn(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _alert_status_after_decide(decision: str, conclusion: str) -> str:
    if decision == "reject":
        return "pending"
    if decision == "submit":
        return "pending_review"
    if decision == "modify":
        return "modified"
    if conclusion == "exclude":
        return "closed"
    if conclusion == "observe":
        return "monitoring"
    return "ready_to_file"


def _case_status_after_decide(decision: str, conclusion: str) -> str:
    if decision == "reject":
        return "OPEN"
    if decision == "submit":
        return "PENDING_REVIEW"
    if decision != "confirm":
        return "PENDING_REVIEW"
    if conclusion in {"exclude", "observe"}:
        return "CLOSED"
    return "PENDING_REVIEW"


def get_investigation(db: Session, alert_id: str) -> Investigation | None:
    return db.query(Investigation).filter(Investigation.alert_id == alert_id).first()


_INVESTIGATE_GUARD = threading.Lock()
_INVESTIGATE_RUNNING: set[str] = set()
INVESTIGATE_BUSY = "本案正在调查"
INVESTIGATE_FAIL = "调查失败，请重试"


def _try_begin_investigation(alert_id: str) -> None:
    with _INVESTIGATE_GUARD:
        if alert_id in _INVESTIGATE_RUNNING:
            raise HTTPException(409, INVESTIGATE_BUSY)
        _INVESTIGATE_RUNNING.add(alert_id)


def _end_investigation(alert_id: str) -> None:
    with _INVESTIGATE_GUARD:
        _INVESTIGATE_RUNNING.discard(alert_id)


def _reset_alert_for_investigate(db: Session, alert: Alert) -> dict:
    """重跑覆盖待复核/已监测状态，签发必须对新草稿重走双控；人工备注与补证清单保留。"""
    leftover = {"human_note": "", "checklist_appended": None, "prior_review": None}
    alert.status = "investigating"
    inv = get_investigation(db, alert.id)
    if inv:
        leftover["human_note"] = inv.human_note or ""
        inv.human_decision = ""
        inv.signed_by_id = ""
        inv.signed_by_name = ""
        inv.decided_at = None
        try:
            payload = json.loads(inv.payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        appended = payload.get("checklist_appended")
        if isinstance(appended, dict):
            leftover["checklist_appended"] = appended
        review = payload.get("human_review") if isinstance(payload.get("human_review"), dict) else {}
        if leftover["human_note"] or review.get("submitted_by_id") or review.get("signed_by_id"):
            leftover["prior_review"] = {
                "human_decision": review.get("decision") or "",
                "submitted_by_id": review.get("submitted_by_id") or "",
                "submitted_by_name": review.get("submitted_by_name") or "",
                "signed_by_id": review.get("signed_by_id") or "",
                "signed_by_name": review.get("signed_by_name") or "",
            }
        if isinstance(payload.get("human_review"), dict):
            payload["human_review"] = {}
        v2 = payload.get("case_v2")
        if isinstance(v2, dict):
            v2["human_decision"] = ""
            v2["status"] = "INVESTIGATING"
            payload["case_v2"] = v2
        inv.payload_json = json.dumps(payload, ensure_ascii=False)
    rec = db.get(AmlCase, alert.id)
    if rec:
        rec.human_decision = ""
        rec.status = "OPEN"
        rec.updated_at = utcnow()
    return leftover


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_sqlite(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
        seed_prompt_versions(db)
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="循证慧查", version="3.0.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def demo_token_guard(request: Request, call_next):
    path = request.url.path
    open_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/accounts",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    if path in open_paths or not path.startswith("/api/"):
        return await call_next(request)
    expected = demo_token()
    if expected:
        got = request.headers.get("x-huicha-token") or ""
        if got != expected:
            return JSONResponse(
                {"detail": "需要演示口令（Header X-Huicha-Token）。竞赛原型，不是银行 SSO。"},
                status_code=401,
            )
    return await call_next(request)


def write_audit(db: Session, alert_id: str, actor: str, action: str, detail: str) -> None:
    db.add(AuditLog(alert_id=alert_id, actor=actor, action=action, detail=detail, created_at=utcnow()))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "name": "循证慧查",
        "llm": llm_mode(),
        "model": llm_model() if llm_mode() != "off" else "",
        "stack": "FastAPI + SQLite + React（竞赛原型，非生产 PG/Docker）",
        "version": "3.0.1",
        "data_note": "synthetic",
        "auth": auth_mode(),
        "privacy": {"policy": POLICY_VERSION, "llm_egress": "mask+assert"},
        "cors": cors_origins(),
        "kb_docs": corpus_size(),
        "kb_search_units": search_unit_count(),
        "kb_retrieval": retrieval_mode(),
        "contest": {
            "headline": "AI 负责推理，规则负责边界，证据负责事实，人负责最终决策。",
            "demo_case": "ALT-L-20260910",
            "memory_points": ["证据闭环", "安全兜底", "人工负责"],
            "playbook": "答辩作战手册.md",
        },
        "limitations": [
            "无银行 SSO；演示登录绑定签发人与导出，HUICHA_DEMO_TOKEN 为空则读接口开放",
            "SQLite 文件库，调查载荷明文存储，不是银行级加密",
            "LLM 出站经 PrivacyMap 脱敏并检漏；工作台展示受控明文",
            "知识库含现行法律规章官方条款（按条切块）+ 作业转述；混合检索（关键词 + 字符 TF-IDF），目录条数见 kb_docs，检索单元见 kb_search_units",
            "告警为合成数据，gold_label 与规则模板同源，不是生产准确率",
            "人效对照未完成前不得填写效率提升百分比",
        ],
    }


class LoginBody(BaseModel):
    staff_id: str
    password: str


@app.get("/api/auth/accounts")
def auth_accounts():
    return {"accounts": list_demo_accounts(), "note": "竞赛演示账号，口令均为 aml123"}


@app.post("/api/auth/login")
def auth_login(body: LoginBody):
    token, user = create_session(body.staff_id, body.password)
    return {"ok": True, "token": token, "user": user.as_dict()}


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.headers.get("x-huicha-session") or ""
    destroy_session(token)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request):
    user = resolve_session(request.headers.get("x-huicha-session"))
    if not user:
        raise HTTPException(401, "未登录或会话已过期")
    return {"ok": True, "user": user.as_dict()}


@app.get("/api/kb")
def kb_index(q: str = ""):
    docs = list_knowledge()
    hits = search_knowledge(q, top_k=8) if q.strip() else docs
    return {
        "query": q,
        "total": len(docs),
        "search_units": search_unit_count(),
        "hits": hits,
        "retrieval": retrieval_mode(),
        "data_note": "official-statute+playbook",
    }


@app.get("/api/kb/{doc_id}")
def kb_doc(doc_id: str):
    doc = get_knowledge(doc_id)
    if not doc:
        raise HTTPException(404, "知识库条目不存在")
    return doc


@app.get("/api/alerts")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.query(Alert).order_by(Alert.created_at.desc()).all()
    inv_map = {
        i.alert_id: i
        for i in db.query(Investigation).filter(Investigation.alert_id.in_([a.id for a in rows])).all()
    } if rows else {}
    cust_ids = {a.customer_id for a in rows}
    cust_map = {
        c.id: c for c in db.query(Customer).filter(Customer.id.in_(cust_ids)).all()
    } if cust_ids else {}
    out = []
    for a in rows:
        c = cust_map.get(a.customer_id)
        inv = inv_map.get(a.id)
        out.append(
            {
                "id": a.id,
                "case_no": case_no(a.id, a.created_at),
                "title": a.title,
                "alert_type": a.alert_type,
                "amount": a.amount,
                "created_at": a.created_at,
                "status": a.status,
                "demo_tag": a.demo_tag,
                "customer_name": c.name if c else "",
                "customer_id": a.customer_id,
                "account_masked": mask_account(a.account_id),
                "upstream": a.upstream,
                "has_draft": bool(inv),
                "conclusion": inv.conclusion if inv else "",
                "human_decision": inv.human_decision if inv else "",
            }
        )
    return out


@app.get("/api/cases")
def list_cases(db: Session = Depends(get_db)):
    """案件列表 = 告警队列（1:1）。"""
    return list_alerts(db)


@app.get("/api/alerts/{alert_id}")
def get_alert_detail(alert_id: str, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    inv = get_investigation(db, alert_id)
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.alert_id == alert_id)
        .order_by(AuditLog.id.asc())
        .all()
    )
    payload = json.loads(inv.payload_json) if inv else None
    payload, human_note = scrub_payload_checklist(payload, inv.human_note if inv else "")
    return {
        "alert": {
            "id": alert.id,
            "case_no": case_no(alert.id, alert.created_at),
            "title": alert.title,
            "alert_type": alert.alert_type,
            "amount": alert.amount,
            "created_at": alert.created_at,
            "status": alert.status,
            "demo_tag": alert.demo_tag,
            "account_id": alert.account_id,
            "account_masked": mask_account(alert.account_id),
            "customer_id": alert.customer_id,
            "upstream": alert.upstream,
        },
        "investigation": payload,
        "human_decision": inv.human_decision if inv else "",
        "human_note": human_note,
        "signed_by_id": (inv.signed_by_id if inv else "") or "",
        "signed_by_name": (inv.signed_by_name if inv else "") or "",
        "submitted_by_id": ((payload or {}).get("human_review") or {}).get("submitted_by_id") or "",
        "submitted_by_name": ((payload or {}).get("human_review") or {}).get("submitted_by_name") or "",
        "decided_at": format_cn(inv.decided_at) if inv else "",
        "audit": [
            {
                "id": x.id,
                "actor": x.actor,
                "action": x.action,
                "detail": x.detail,
                "created_at": format_cn(x.created_at),
            }
            for x in logs
        ],
    }


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    return get_alert_detail(case_id, db)


@app.post("/api/alerts/{alert_id}/investigate")
def investigate(
    alert_id: str,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
    experiment_mode: bool = False,
    db: Session = Depends(get_db),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    _try_begin_investigation(alert_id)
    try:
        leftover = _reset_alert_for_investigate(db, alert)
        db.commit()
        try:
            result = run_investigation(
                db,
                alert_id,
                use_challenger=use_challenger,
                inject_hallucination=inject_hallucination,
                experiment_mode=experiment_mode,
            )
        except PrivacyLeakError as e:
            raise HTTPException(502, str(e)) from e
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from e
        _finalize_investigation(
            db,
            alert,
            result,
            use_challenger=use_challenger,
            inject_hallucination=inject_hallucination,
            experiment_mode=experiment_mode,
            leftover=leftover,
        )
        db.commit()
        return result
    finally:
        _end_investigation(alert_id)


def _finalize_investigation(
    db: Session,
    alert: Alert,
    result: dict,
    *,
    use_challenger: bool,
    inject_hallucination: bool,
    experiment_mode: bool,
    leftover: dict | None = None,
) -> None:
    alert_id = alert.id
    carry = leftover or {}
    kept_note = str(carry.get("human_note") or "")
    if kept_note:
        report = result.setdefault("report", {})
        apply_remarks_to_report(report, kept_note)
        result["report"] = report
    appended = carry.get("checklist_appended")
    if isinstance(appended, dict) and appended.get("item_ids"):
        result["checklist_appended"] = appended
        attach_checklist(result, human_note=kept_note)
    prior = carry.get("prior_review")
    if prior:
        result["prior_human_review"] = prior
    inv = get_investigation(db, alert_id)
    blob = json.dumps(result, ensure_ascii=False)
    if inv:
        inv.payload_json = blob
        inv.conclusion = result["conclusion"]
        inv.human_decision = ""
        inv.human_note = kept_note
        inv.signed_by_id = ""
        inv.signed_by_name = ""
        inv.decided_at = None
    else:
        inv = Investigation(
            alert_id=alert_id,
            payload_json=blob,
            conclusion=result["conclusion"],
            human_note=kept_note,
        )
        db.add(inv)
    alert.status = "investigating"
    scoring = result.get("scoring") or {}
    run = result.get("challenger_run") or {}
    validator = result.get("validator_result") or {}
    tools = "、".join(f"{c['tool']} {c['records']} 条" for c in result["tool_trace"])
    write_audit(
        db,
        alert_id,
        "agent",
        "investigate",
        json.dumps(
            {
                "summary": (
                    f"生成调查草稿，建议结论「{result['conclusion_label']}」，"
                    f"慧查agent{'开启' if use_challenger else '关闭'}，"
                    f"{'实验模式' if experiment_mode else '正常模式'}，"
                    f"幻觉演示{'开启' if inject_hallucination else '关闭'}。{tools}"
                ),
                "case_id": alert_id,
                "timestamp": format_cn(utcnow()),
                "agent": "pipeline",
                "model": (result.get("llm") or {}).get("model") or "",
                "prompt_version": (result.get("prompt_versions") or {}).get("judge") or "",
                "prompt_versions": result.get("prompt_versions") or {},
                "challenger_enabled": use_challenger,
                "experiment_mode": experiment_mode,
                "challenger_off_reason": (
                    ""
                    if use_challenger
                    else ("实验模式消融" if experiment_mode else "请求关闭 AI反向质询")
                ),
                "rule_prior": scoring.get("rule_prior"),
                "llm_delta": scoring.get("llm_delta"),
                "final_score": scoring.get("final"),
                "rule_baseline": result.get("rule_baseline") or {},
                "judge_decision": result.get("judge") or {},
                "policy_guardrails": result.get("policy_guardrails") or {},
                "evidence_ids": [e.get("id") for e in (result.get("evidence") or [])[:20]],
                "counter_evidence_ids": (result.get("structured_report") or {}).get("counter_evidence_ids") or [],
                "validator_result": validator,
                "counterfactual": result.get("counterfactual") or {},
                "human_decision": "",
                "privacy": result.get("privacy") or {},
                "data_note": "synthetic",
            },
            ensure_ascii=False,
        ),
    )
    if validator.get("overbound") or run.get("delta_clamped") or not validator.get("passed", True):
        write_audit(
            db,
            alert_id,
            "agent",
            "validator",
            json.dumps(
                {
                    "summary": validator.get("reason") or "Evidence Validator 已处理越界/无效 Claim",
                    "case_id": alert_id,
                    "challenger_enabled": use_challenger,
                    "llm_delta": scoring.get("llm_delta"),
                    "validator_result": validator,
                    "data_note": "synthetic",
                },
                ensure_ascii=False,
            ),
        )


def _sse_pack(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/alerts/{alert_id}/investigate/stream")
def investigate_stream(
    alert_id: str,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
    experiment_mode: bool = False,
    db: Session = Depends(get_db),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    _try_begin_investigation(alert_id)
    events: queue.Queue = queue.Queue()

    def worker() -> None:
        session = SessionLocal()
        try:
            row = session.get(Alert, alert_id)
            if not row:
                events.put({"event": "error", "detail": INVESTIGATE_FAIL})
                return

            def emit(event: dict) -> None:
                events.put(event)

            leftover = _reset_alert_for_investigate(session, row)
            session.commit()
            result = run_investigation(
                session,
                alert_id,
                use_challenger=use_challenger,
                inject_hallucination=inject_hallucination,
                experiment_mode=experiment_mode,
                emit=emit,
            )
            _finalize_investigation(
                session,
                row,
                result,
                use_challenger=use_challenger,
                inject_hallucination=inject_hallucination,
                experiment_mode=experiment_mode,
                leftover=leftover,
            )
            session.commit()
            events.put({"event": "done", "payload": result})
        except PrivacyLeakError:
            session.rollback()
            events.put({"event": "error", "detail": "出站检漏失败，本轮已中止"})
        except RuntimeError:
            session.rollback()
            events.put({"event": "error", "detail": INVESTIGATE_FAIL})
        except Exception:
            session.rollback()
            events.put({"event": "error", "detail": INVESTIGATE_FAIL})
        finally:
            session.close()
            _end_investigation(alert_id)
            events.put(None)

    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception:
        _end_investigation(alert_id)
        raise

    def generate():
        while True:
            item = events.get()
            if item is None:
                break
            event = item.get("event") or "message"
            yield _sse_pack(event, item)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class DecideBody(BaseModel):
    decision: str
    note: str = ""


class NoteBody(BaseModel):
    note: str = ""


class ChecklistAppendBody(BaseModel):
    item_ids: list[str] = []


def _checklist_payload(db: Session, alert_id: str) -> tuple[Alert, Investigation, dict]:
    alert = db.get(Alert, alert_id)
    inv = get_investigation(db, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    if not inv:
        raise HTTPException(400, "请先生成调查草稿")
    payload = json.loads(inv.payload_json)
    txs = payload.get("transactions") or []
    account_id = (payload.get("alert") or {}).get("account_id") or alert.account_id
    peers = enrich_counterparties(db, account_id, txs, payload.get("graph") or {})
    attach_checklist(payload, counterparties=peers, human_note=inv.human_note or "")
    return alert, inv, payload


@app.get("/api/alerts/{alert_id}/checklist")
def get_checklist(alert_id: str, db: Session = Depends(get_db)):
    alert, inv, payload = _checklist_payload(db, alert_id)
    blob = payload.get("checklist") or {}
    _payload, human_note = scrub_payload_checklist(payload, inv.human_note or "")
    return {
        "alert_id": alert_id,
        "recommendation": blob.get("recommendation") or (payload.get("case_v2") or {}).get("recommendation") or "",
        "can_sign": payload.get("can_sign"),
        "human_note": human_note,
        "human_decision": inv.human_decision or "",
        **blob,
    }


@app.get("/api/cases/{case_id}/checklist")
def get_case_checklist(case_id: str, db: Session = Depends(get_db)):
    return get_checklist(case_id, db)


@app.post("/api/alerts/{alert_id}/checklist/append")
def append_checklist(alert_id: str, body: ChecklistAppendBody, request: Request, db: Session = Depends(get_db)):
    ids = [x.strip() for x in (body.item_ids or []) if str(x).strip()]
    if not ids:
        raise HTTPException(400, "请至少选择一条待补证项")
    alert, inv, payload = _checklist_payload(db, alert_id)
    items = (payload.get("checklist") or {}).get("items") or generate_checklist({})
    by_id = {it["id"]: it for it in items}
    picked = [by_id[i] for i in ids if i in by_id]
    if not picked:
        raise HTTPException(400, "所选条目不在本清单中")
    note = merge_note(inv.human_note or "", picked)
    inv.human_note = note
    already = list((payload.get("checklist_appended") or {}).get("item_ids") or [])
    for i in ids:
        if i not in already:
            already.append(i)
    payload["checklist_appended"] = {
        "item_ids": already,
        "at": format_cn(utcnow()),
        "text": note,
    }
    report = payload.setdefault("report", {})
    review = payload.setdefault("human_review", {})
    apply_remarks_to_report(report, note, entries=review.get("notes") or None)
    review["note"] = note
    peers = enrich_counterparties(
        db,
        (payload.get("alert") or {}).get("account_id") or alert.account_id,
        payload.get("transactions") or [],
        payload.get("graph") or {},
    )
    attach_checklist(payload, counterparties=peers, human_note=note)
    inv.payload_json = json.dumps(payload, ensure_ascii=False)
    user = resolve_session(request.headers.get("x-huicha-session"))
    actor = user.label() if user else "investigator"
    write_audit(
        db,
        alert_id,
        actor,
        "checklist",
        json.dumps(
            {
                "summary": f"将 {len(picked)} 条补证项写入草稿备注",
                "item_ids": [p["id"] for p in picked],
                "case_id": alert_id,
                "human_decision": inv.human_decision or "",
                "data_note": "synthetic",
            },
            ensure_ascii=False,
        ),
    )
    db.commit()
    blob = payload.get("checklist") or {}
    return {
        "ok": True,
        "alert_id": alert_id,
        "human_note": note,
        "appended": [p["id"] for p in picked],
        "final_action": "draft_only",
        "note": "已写入调查员草稿备注，系统不会自动报送。",
        **blob,
    }


@app.post("/api/alerts/{alert_id}/note")
def save_human_note(alert_id: str, body: NoteBody, request: Request, db: Session = Depends(get_db)):
    """不能直接签发时，把人工判断写入草稿备注，不改变处置/签发状态。"""
    user = require_user(request)
    alert = db.get(Alert, alert_id)
    inv = get_investigation(db, alert_id)
    if not alert or not inv:
        raise HTTPException(400, "请先生成调查草稿")
    if (inv.human_decision or "") in FINALIZED:
        raise HTTPException(400, "本案已签发，不能改写草稿备注")
    note = sanitize_note(body.note or "")
    if not note:
        raise HTTPException(400, "请填写备注")
    if len(note) > NOTE_MAX_LEN:
        raise HTTPException(400, f"备注不超过{NOTE_MAX_LEN}字")
    payload = json.loads(inv.payload_json)
    review = dict(payload.get("human_review") or {})
    entries = [row for row in (review.get("notes") or []) if isinstance(row, dict)]
    last = entries[-1] if entries else None
    blockers = snapshot_blockers(payload)
    warnings = check_note_facts(note, payload)
    stamped = format_cn(utcnow())
    if not last or (last.get("text") or "").strip() != note:
        entries.append(
            {
                "text": note,
                "at": stamped,
                "by_id": user.staff_id,
                "by_name": user.name,
                "blockers": blockers,
                "fact_warnings": warnings,
            }
        )
    else:
        last["at"] = stamped
        last["by_id"] = user.staff_id
        last["by_name"] = user.name
        last["blockers"] = blockers
        last["fact_warnings"] = warnings
    review["notes"] = entries
    review["note"] = note
    review["note_at"] = stamped
    review["note_by_id"] = user.staff_id
    review["note_by_name"] = user.name
    review["note_blockers"] = blockers
    payload["human_review"] = review
    inv.human_note = compose_human_note(inv.human_note or "", note)
    report = payload.setdefault("report", {})
    apply_remarks_to_report(report, inv.human_note, entries=entries)
    peers = enrich_counterparties(
        db,
        (payload.get("alert") or {}).get("account_id") or alert.account_id,
        payload.get("transactions") or [],
        payload.get("graph") or {},
    )
    attach_checklist(payload, counterparties=peers, human_note=inv.human_note or "")
    inv.payload_json = json.dumps(payload, ensure_ascii=False)
    write_audit(
        db,
        alert_id,
        user.label(),
        "note",
        json.dumps(
            {
                "summary": "写入草稿备注（未签发）",
                "case_id": alert_id,
                "human_decision": inv.human_decision or "",
                "can_sign": bool(payload.get("can_sign")),
                "note": note,
                "blockers": blockers,
                "fact_warnings": warnings,
                "data_note": "synthetic",
            },
            ensure_ascii=False,
        ),
    )
    db.commit()
    return {
        "ok": True,
        "alert_id": alert_id,
        "human_note": inv.human_note or "",
        "human_decision": inv.human_decision or "",
        "can_sign": bool(payload.get("can_sign")),
        "notes": entries,
        "note_blockers": blockers,
        "note_fact_warnings": warnings,
        "final_action": "draft_only",
        "note": "已写入草稿备注，未改变签发状态，系统不会自动报送。",
    }


@app.post("/api/alerts/{alert_id}/decide")
def decide(alert_id: str, body: DecideBody, request: Request, db: Session = Depends(get_db)):
    user = require_user(request)
    alert = db.get(Alert, alert_id)
    inv = get_investigation(db, alert_id)
    if not alert or not inv:
        raise HTTPException(400, "请先生成调查草稿")
    payload = json.loads(inv.payload_json)
    review = dict(payload.get("human_review") or {})
    submitted_by_id = review.get("submitted_by_id") or ""
    if inv.human_decision == "submit":
        submitted_by_id = submitted_by_id or inv.signed_by_id or ""
    assert_decision_allowed(
        user,
        body.decision,
        current_decision=inv.human_decision or "",
        can_sign=bool(payload.get("can_sign")),
        note=body.note or "",
        submitted_by_id=submitted_by_id,
        sign_blockers=payload.get("sign_blockers") or [],
    )
    inv.human_decision = body.decision
    inv.human_note = body.note
    if body.decision in {"confirm", "modify"}:
        inv.signed_by_id = user.staff_id
        inv.signed_by_name = user.name
    elif body.decision == "submit":
        inv.signed_by_id = ""
        inv.signed_by_name = ""
    inv.decided_at = utcnow()
    alert.status = _alert_status_after_decide(body.decision, payload.get("conclusion") or "")
    v2 = payload.setdefault("case_v2", {})
    v2["status"] = _case_status_after_decide(body.decision, payload.get("conclusion") or "")
    v2["human_decision"] = body.decision
    if body.decision == "submit":
        review["submitted_by_id"] = user.staff_id
        review["submitted_by_name"] = user.name
        review["submitted_at"] = format_cn(inv.decided_at)
        review["submit_note"] = body.note
        review["signed_by_id"] = ""
        review["signed_by_name"] = ""
        review["signed_by"] = ""
    review.update(
        {
            "decision": body.decision,
            "note": body.note,
            "at": format_cn(inv.decided_at),
            "acted_by_id": user.staff_id,
            "acted_by_name": user.name,
        }
    )
    if body.decision in {"confirm", "modify"}:
        review["signed_by_id"] = user.staff_id
        review["signed_by_name"] = user.name
        review["signed_by"] = user.label()
    payload["human_review"] = review
    inv.payload_json = json.dumps(payload, ensure_ascii=False)
    note = f"：{body.note}" if body.note else ""
    scoring = payload.get("scoring") or {}
    write_audit(
        db,
        alert_id,
        user.label(),
        "decide",
        json.dumps(
            {
                "summary": f"{DECIDE_LABEL[body.decision]}{note}",
                "case_id": alert_id,
                "timestamp": format_cn(inv.decided_at),
                "agent": "human",
                "challenger_enabled": payload.get("case_challenger_enabled", payload.get("use_challenger")),
                "experiment_mode": payload.get("experiment_mode", False),
                "rule_prior": scoring.get("rule_prior"),
                "llm_delta": scoring.get("llm_delta"),
                "final_score": scoring.get("final"),
                "human_decision": body.decision,
                "data_note": "synthetic",
            },
            ensure_ascii=False,
        ),
    )
    reco = (payload.get("case_v2") or {}).get("recommendation") or ""
    persist_human_decision(
        db,
        alert_id,
        body.decision,
        body.note,
        reco,
        signed_by_id=user.staff_id if body.decision in {"confirm", "modify"} else "",
        signed_by_name=user.name if body.decision in {"confirm", "modify"} else "",
    )
    db.commit()
    return {
        "ok": True,
        "status": alert.status,
        "human_decision": body.decision,
        "signed_by_id": inv.signed_by_id or "",
        "signed_by_name": inv.signed_by_name or "",
        "ai_recommendation": reco,
        "final_action": "human_only",
        "note": "AI 建议已记录，最终处置以人工为准，系统不会自动报送。",
    }


@app.get("/api/metrics")
def metrics(db: Session = Depends(get_db)):
    alerts = db.query(Alert).all()
    invs = db.query(Investigation).all()
    by_status = {}
    for a in alerts:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    signed = sum(1 for i in invs if i.human_decision == "confirm")
    labeled = sum(1 for a in alerts if (a.gold_label or ""))
    parsed_pairs = []
    for inv in invs:
        try:
            parsed_pairs.append((inv, json.loads(inv.payload_json or "{}")))
        except (TypeError, json.JSONDecodeError):
            continue
    parsed_payloads = [payload for _inv, payload in parsed_pairs]
    validations = [p.get("judge_validation") or {} for p in parsed_payloads]
    validated = [v for v in validations if v.get("score_kind") == "evidence_contract"]
    rejected_claims = [
        claim
        for p in parsed_payloads
        for claim in (p.get("rejected_claims") or [])
    ]
    fact_blocked = sum(1 for p in parsed_payloads if p.get("fact_issues"))
    elapsed = [float(p["elapsed_ms"]) for p in parsed_payloads if p.get("elapsed_ms") is not None]
    tokens = sum(investigation_tokens(p) for p in parsed_payloads)
    validation_audits = db.query(AuditLog).filter(AuditLog.action == "validator").count()
    decision_audits = db.query(AuditLog).filter(AuditLog.action == "decide").count()
    closed = note_metrics(parsed_pairs)
    return {
        "alerts": len(alerts),
        "labeled": labeled,
        "labeled_note": "gold_label 由模板写入，与规则同源，不是独立人工标注",
        "store": "sqlite",
        "drafts": len(invs),
        "signed": signed,
        "tokens": tokens,
        "by_status": by_status,
        "quality": {
            "evidence_contract_pass_rate": round(
                sum(1 for v in validated if v.get("passed")) / len(validated), 4
            ) if validated else None,
            "evidence_contract_checked": len(validated),
            "rejected_claims": len(rejected_claims),
            "fact_check_blocked": fact_blocked,
            "avg_investigation_ms": round(sum(elapsed) / len(elapsed)) if elapsed else None,
            "audited_validations": validation_audits,
            "human_decisions": decision_audits,
            **closed,
        },
        "quality_note": "质量指标来自当前合成案件草稿与审计记录，不代表生产准确率",
    }


@app.get("/api/feedback")
def feedback(db: Session = Depends(get_db)):
    """人机闭环看板：采纳/修改/驳回率，及人工改结论与 Agent 建议对照。"""
    invs = db.query(Investigation).all()
    alerts = {a.id: a for a in db.query(Alert).all()}
    counts = {"confirm": 0, "modify": 0, "reject": 0, "submit": 0, "undecided": 0}
    by_type: dict[str, dict] = {}
    flipped = []
    for inv in invs:
        d = inv.human_decision or ""
        if d in counts:
            counts[d] += 1
        else:
            counts["undecided"] += 1
        alert = alerts.get(inv.alert_id)
        atype = alert.alert_type if alert else "未知"
        bucket = by_type.setdefault(atype, {"confirm": 0, "modify": 0, "reject": 0, "total": 0})
        if d in {"confirm", "modify", "reject"}:
            bucket[d] += 1
            bucket["total"] += 1
        if d in {"modify", "reject"} and inv.conclusion:
            flipped.append(
                {
                    "alert_id": inv.alert_id,
                    "alert_type": atype,
                    "agent_conclusion": inv.conclusion,
                    "human_decision": d,
                    "note": (inv.human_note or "")[:120],
                }
            )
    decided = counts["confirm"] + counts["modify"] + counts["reject"]
    return {
        "decisions": counts,
        "rates": {
            "confirm": round(counts["confirm"] / decided, 4) if decided else 0,
            "modify": round(counts["modify"] / decided, 4) if decided else 0,
            "reject": round(counts["reject"] / decided, 4) if decided else 0,
        },
        "by_alert_type": by_type,
        "human_flipped": flipped[:50],
        "note": "信号已入库供离线优化；竞赛原型不做在线再训练。",
    }


@app.get("/api/alerts/{alert_id}/export")
def export_report(alert_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request)
    inv = get_investigation(db, alert_id)
    if not inv:
        raise HTTPException(404, "尚无草稿")
    payload = json.loads(inv.payload_json)
    payload, human_note = scrub_payload_checklist(payload, inv.human_note or "")
    report = payload.get("report", {})
    signed = inv.human_decision or ""
    signed_line = DECIDE_LABEL.get(signed, signed) if signed else "否（本文件仅为草稿）"
    review = payload.get("human_review") or {}
    submitted_name = review.get("submitted_by_name") or "（未提交）"
    if signed in {"confirm", "modify"} and (inv.signed_by_name or inv.signed_by_id):
        if inv.signed_by_name and inv.signed_by_id:
            signer = f"{inv.signed_by_name}（{inv.signed_by_id}）"
        else:
            signer = inv.signed_by_name or inv.signed_by_id
    else:
        signer = "（未签发）"
    v2 = payload.get("case_v2") or {}
    priv = payload.get("privacy") or {}
    rejected = payload.get("rejected_claims") or []
    verified = [
        c
        for c in (payload.get("challenger") or [])
        if (c.get("validation") or {}).get("score_kind") == "predicate_verified"
    ]
    note_entries = [row for row in (review.get("notes") or []) if isinstance(row, dict) and (row.get("text") or "").strip()]
    note_history = []
    if note_entries:
        note_history.append("- 备注记录：")
        for row in note_entries:
            who = " ".join(part for part in (row.get("at") or "", row.get("by_name") or "") if part)
            note_history.append(f"  - {who}：{row.get('text')}" if who else f"  - {row.get('text')}")
            codes = "、".join(
                str(b.get("code") or "")
                for b in (row.get("blockers") or [])
                if isinstance(b, dict) and b.get("code")
            )
            if codes:
                note_history.append(f"    当时拦截：{codes}")
    lines = [
        "# 循证慧查 可疑交易调查草稿（非报送报文）",
        "",
        f"- 告警：{alert_id}",
        f"- 案件号：{case_no(alert_id, (payload.get('alert') or {}).get('created_at') or '')}",
        f"- 建议结论：{payload.get('conclusion_label')}",
        f"- AI 建议档：{v2.get('recommendation') or ''}",
        f"- 风险等级：{v2.get('risk_level') or ''}",
        f"- 规则对照分：{(payload.get('rule_baseline') or {}).get('score', '—')}（仅对照，不与 AI 相加）",
        f"- AI 自评把握度：{payload.get('confidence')}（{payload.get('confidence_kind') or 'llm_self_assessed_not_calibrated'}，非校准概率）",
        f"- 人工签发：{signed_line}",
        f"- 提交人：{submitted_name}",
        f"- 签发人：{signer}",
        f"- 调查员意见：{(human_note or '').strip() or '（无）'}",
        *note_history,
        f"- 补证清单：缺失 {(payload.get('checklist') or {}).get('missing_count', '—')} 项（规则提示，非报送）",
        f"- Challenger：{'开' if payload.get('use_challenger', True) else '关'}",
        f"- 数据：{payload.get('data_note') or 'synthetic'}",
        f"- 进模脱敏：{priv.get('policy') or 'privacy_v2'} · 姓名 {priv.get('masked_names', 0)} · 账号 {priv.get('masked_accounts', 0)} · 客户号 {priv.get('masked_customer_ids', 0)} · 出站 {priv.get('egress_calls', 0)} 次",
        f"- 导出人：{user.label()}",
        "",
        report.get("full_text", ""),
        "",
        "## 知识库引用",
        *[f"- {h['id']} {h.get('title','')}（{h.get('source','')}）" for h in payload.get("kb_hits", [])],
        "",
        "## 证据编号",
        *[f"- {e['id']} {e.get('summary','')}" for e in payload.get("evidence", [])[:30]],
        "",
        "## Validator 已核验谓词",
        *(
            [
                f"- {c.get('predicate') or ''} {c.get('claim') or ''}（{(c.get('validation') or {}).get('reason') or ''}）"
                for c in verified[:12]
            ]
            if verified
            else ["- （无）"]
        ),
        "",
        "## Validator 拒绝项",
        *(
            [f"- {r.get('validation', {}).get('reason') or r.get('claim') or r}" for r in rejected[:12]]
            if rejected
            else ["- （无）"]
        ),
        "",
        "—— Agent 不可自动报送，须调查员签发 ——",
    ]
    write_audit(
        db,
        alert_id,
        user.label(),
        "export",
        json.dumps(
            {
                "summary": f"{user.label()} 导出调查底稿（非报送报文）",
                "signed": bool(signed),
                "privacy": {"policy": priv.get("policy"), "egress_calls": priv.get("egress_calls")},
                "data_note": "synthetic",
            },
            ensure_ascii=False,
        ),
    )
    db.commit()
    filename = f"huicha-{alert_id}.md"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    }
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )
