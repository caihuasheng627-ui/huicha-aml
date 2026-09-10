import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .agents import run_investigation
from .database import Base, SessionLocal, engine, get_db
from .knowledge import list_knowledge, search_knowledge
from .llm import llm_configured, llm_model
from .models import Alert, AuditLog, Customer, Investigation, utcnow
from .seed import seed_if_empty

DECIDE_LABEL = {
    "confirm": "已签发草稿",
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


def get_investigation(db: Session, alert_id: str) -> Investigation | None:
    return db.query(Investigation).filter(Investigation.alert_id == alert_id).first()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    yield


app = FastAPI(title="慧查 AML", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def write_audit(db: Session, alert_id: str, actor: str, action: str, detail: str) -> None:
    db.add(AuditLog(alert_id=alert_id, actor=actor, action=action, detail=detail, created_at=utcnow()))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "name": "慧查 AML",
        "llm": "bailian" if llm_configured() else "off",
        "model": llm_model() if llm_configured() else "",
        "stack": "FastAPI + SQLite + React（竞赛原型，非生产 PG/Docker）",
    }


@app.get("/api/kb")
def kb_index(q: str = ""):
    docs = list_knowledge()
    hits = search_knowledge(q, top_k=8) if q.strip() else docs
    return {"query": q, "total": len(docs), "hits": hits}


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
                "title": a.title,
                "alert_type": a.alert_type,
                "amount": a.amount,
                "created_at": a.created_at,
                "status": a.status,
                "demo_tag": a.demo_tag,
                "customer_name": c.name if c else "",
                "customer_id": a.customer_id,
                "upstream": a.upstream,
                "has_draft": bool(inv),
                "conclusion": inv.conclusion if inv else "",
                "human_decision": inv.human_decision if inv else "",
            }
        )
    return out


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
    return {
        "alert": {
            "id": alert.id,
            "title": alert.title,
            "alert_type": alert.alert_type,
            "amount": alert.amount,
            "created_at": alert.created_at,
            "status": alert.status,
            "demo_tag": alert.demo_tag,
            "account_id": alert.account_id,
            "customer_id": alert.customer_id,
            "upstream": alert.upstream,
        },
        "investigation": payload,
        "human_decision": inv.human_decision if inv else "",
        "human_note": inv.human_note if inv else "",
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


@app.post("/api/alerts/{alert_id}/investigate")
def investigate(
    alert_id: str,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
    db: Session = Depends(get_db),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    try:
        result = run_investigation(
            db,
            alert_id,
            use_challenger=use_challenger,
            inject_hallucination=inject_hallucination,
        )
    except RuntimeError as e:
        raise HTTPException(502, str(e)) from e
    inv = get_investigation(db, alert_id)
    blob = json.dumps(result, ensure_ascii=False)
    if inv:
        inv.payload_json = blob
        inv.conclusion = result["conclusion"]
        inv.human_decision = ""
        inv.human_note = ""
        inv.decided_at = None
    else:
        inv = Investigation(alert_id=alert_id, payload_json=blob, conclusion=result["conclusion"])
        db.add(inv)
    if alert.status in {"pending", "closed", "ready_to_file", "modified"}:
        alert.status = "investigating"
    tools = "、".join(f"{c['tool']} {c['records']} 条" for c in result["tool_trace"])
    write_audit(
        db,
        alert_id,
        "agent",
        "investigate",
        f"生成调查草稿，建议结论「{result['conclusion_label']}」，"
        f"质疑复核{'开启' if use_challenger else '关闭'}，"
        f"幻觉演示{'开启' if inject_hallucination else '关闭'}。{tools}",
    )
    db.commit()
    return result


class DecideBody(BaseModel):
    decision: str
    note: str = ""


@app.post("/api/alerts/{alert_id}/decide")
def decide(alert_id: str, body: DecideBody, db: Session = Depends(get_db)):
    if body.decision not in {"confirm", "modify", "reject"}:
        raise HTTPException(400, "decision 必须是 confirm / modify / reject")
    alert = db.get(Alert, alert_id)
    inv = get_investigation(db, alert_id)
    if not alert or not inv:
        raise HTTPException(400, "请先生成调查草稿")
    payload = json.loads(inv.payload_json)
    if body.decision == "confirm" and not payload.get("can_sign"):
        raise HTTPException(400, "事实回查未通过，不能签发")
    if body.decision == "modify" and not payload.get("can_sign") and not body.note.strip():
        raise HTTPException(400, "事实回查未通过时，「修改后采纳」须填写修改说明")
    inv.human_decision = body.decision
    inv.human_note = body.note
    inv.decided_at = utcnow()
    if body.decision == "confirm":
        alert.status = "closed" if payload["conclusion"] == "exclude" else "ready_to_file"
    elif body.decision == "reject":
        alert.status = "pending"
    else:
        alert.status = "modified"
    note = f"：{body.note}" if body.note else ""
    write_audit(
        db,
        alert_id,
        "investigator",
        "decide",
        f"{DECIDE_LABEL[body.decision]}{note}",
    )
    db.commit()
    return {"ok": True, "status": alert.status, "human_decision": body.decision}


@app.get("/api/metrics")
def metrics(db: Session = Depends(get_db)):
    alerts = db.query(Alert).all()
    invs = db.query(Investigation).all()
    by_status = {}
    for a in alerts:
        by_status[a.status] = by_status.get(a.status, 0) + 1
    signed = sum(1 for i in invs if i.human_decision == "confirm")
    labeled = sum(1 for a in alerts if (a.gold_label or ""))
    return {
        "alerts": len(alerts),
        "labeled": labeled,
        "drafts": len(invs),
        "signed": signed,
        "by_status": by_status,
    }


@app.get("/api/feedback")
def feedback(db: Session = Depends(get_db)):
    """人机闭环看板：采纳/修改/驳回率，及人工改结论与 Agent 建议对照。"""
    invs = db.query(Investigation).all()
    alerts = {a.id: a for a in db.query(Alert).all()}
    counts = {"confirm": 0, "modify": 0, "reject": 0, "undecided": 0}
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
def export_report(alert_id: str, db: Session = Depends(get_db)):
    inv = get_investigation(db, alert_id)
    if not inv:
        raise HTTPException(404, "尚无草稿")
    payload = json.loads(inv.payload_json)
    report = payload.get("report", {})
    lines = [
        "# 慧查 AML 可疑交易调查草稿（非报送报文）",
        "",
        f"- 告警：{alert_id}",
        f"- 建议结论：{payload.get('conclusion_label')}",
        f"- 置信度：{payload.get('confidence')}",
        f"- 人工签发：否（本文件仅为草稿）",
        f"- Challenger：{'开' if payload.get('use_challenger', True) else '关'}",
        "",
        report.get("full_text", ""),
        "",
        "## 知识库引用",
        *[f"- {h['id']} {h.get('title','')}（{h.get('source','')}）" for h in payload.get("kb_hits", [])],
        "",
        "## 证据编号",
        *[f"- {e['id']} {e.get('summary','')}" for e in payload.get("evidence", [])[:30]],
        "",
        "—— Agent 不可自动报送，须调查员签发 ——",
    ]
    filename = f"huicha-{alert_id}.md"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    }
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )
