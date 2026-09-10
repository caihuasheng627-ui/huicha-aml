import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .agents import run_investigation
from .database import Base, SessionLocal, engine, get_db
from .knowledge import list_knowledge, search_knowledge
from .models import Alert, AuditLog, Customer, Investigation
from .seed import seed_if_empty

DECIDE_LABEL = {
    "confirm": "已签发草稿",
    "modify": "修改后采纳",
    "reject": "已驳回",
}


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
    db.add(AuditLog(alert_id=alert_id, actor=actor, action=action, detail=detail))


@app.get("/api/health")
def health():
    return {"ok": True, "name": "慧查 AML"}


@app.get("/api/kb")
def kb_index(q: str = ""):
    docs = list_knowledge()
    hits = search_knowledge(q, top_k=8) if q.strip() else docs
    return {"query": q, "total": len(docs), "hits": hits}


@app.get("/api/alerts")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.query(Alert).order_by(Alert.created_at.desc()).all()
    out = []
    for a in rows:
        c = db.get(Customer, a.customer_id)
        inv = db.query(Investigation).filter(Investigation.alert_id == a.id).first()
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
    inv = db.query(Investigation).filter(Investigation.alert_id == alert_id).first()
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
                "created_at": x.created_at.isoformat(timespec="seconds"),
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
    result = run_investigation(
        db,
        alert_id,
        use_challenger=use_challenger,
        inject_hallucination=inject_hallucination,
    )
    inv = db.query(Investigation).filter(Investigation.alert_id == alert_id).first()
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
    inv = db.query(Investigation).filter(Investigation.alert_id == alert_id).first()
    if not alert or not inv:
        raise HTTPException(400, "请先生成调查草稿")
    payload = json.loads(inv.payload_json)
    if body.decision == "confirm" and not payload.get("can_sign"):
        raise HTTPException(400, "事实回查未通过，不能签发")
    inv.human_decision = body.decision
    inv.human_note = body.note
    inv.decided_at = datetime.utcnow()
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
    return {
        "alerts": len(alerts),
        "drafts": len(invs),
        "signed": signed,
        "by_status": by_status,
    }


@app.get("/api/alerts/{alert_id}/export")
def export_report(alert_id: str, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.alert_id == alert_id).first()
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
    return PlainTextResponse("\n".join(lines), media_type="text/markdown; charset=utf-8")
