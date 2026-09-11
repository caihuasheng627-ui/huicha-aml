from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import Alert, AmlCase, Evidence, HumanDecision, InvestigationStep, Relationship, RiskAssessment, Transaction, utcnow
from .prompts import PROMPTS, prompt_version


def evidence_case_index(db: Session) -> dict[str, str]:
    """source_id / tx_id / evidence_id → case_id。KB 编号跨案共享，不入库映射。"""
    mapping: dict[str, str] = {}
    acct_to_case: dict[str, str] = {}
    for a in db.query(Alert).all():
        mapping[a.id] = a.id
        if a.customer_id:
            mapping[a.customer_id] = a.id
        if a.account_id:
            mapping[a.account_id] = a.id
            acct_to_case[a.account_id] = a.id
    for t in db.query(Transaction).all():
        owner = acct_to_case.get(t.to_account) or acct_to_case.get(t.from_account)
        if owner:
            mapping[t.id] = owner
    for e in db.query(Evidence).all():
        mapping[e.evidence_id] = e.case_id
        for raw in (e.source_id, *(part.strip() for part in (e.raw_reference or "").split(","))):
            if raw and not str(raw).startswith("KB-"):
                mapping[raw] = e.case_id
    return mapping


def persist_investigation(db: Session, result: dict) -> None:
    alert = result.get("alert") or {}
    case_id = alert.get("id") or ""
    if not case_id:
        return
    v2 = result.get("case_v2") or {}
    now = utcnow()
    row = db.get(AmlCase, case_id)
    if not row:
        row = AmlCase(case_id=case_id, alert_id=case_id, customer_id=alert.get("customer_id") or "")
        db.add(row)
    row.customer_id = alert.get("customer_id") or row.customer_id
    row.risk_level = v2.get("risk_level") or ""
    row.risk_score = float((result.get("scoring") or {}).get("final") or 0)
    row.status = v2.get("status") or "INVESTIGATING"
    row.investigation_status = "drafted"
    row.recommendation = v2.get("recommendation") or ""
    row.suspicious_types = ",".join(v2.get("suspicious_types") or [])
    row.data_note = "synthetic"
    row.updated_at = now

    db.query(Evidence).filter(Evidence.case_id == case_id).delete()
    for e in result.get("evidence_graph") or []:
        db.add(
            Evidence(
                evidence_id=e["evidence_id"],
                case_id=case_id,
                evidence_type=e.get("evidence_type") or "",
                source_type=e.get("source_type") or "",
                source_id=e.get("source_id") or "",
                description=e.get("description") or "",
                raw_reference=e.get("raw_reference") or "",
                timestamp=e.get("timestamp") or "",
                reliability=float(e.get("reliability") or 0.9),
                created_by=e.get("created_by") or "collector",
                polarity=e.get("polarity") or "support",
                metadata_json=json.dumps(e.get("metadata") or {}, ensure_ascii=False),
                data_note="synthetic",
            )
        )

    db.query(Relationship).filter(Relationship.case_id == case_id).delete()
    for edge in (result.get("graph") or {}).get("edges") or []:
        db.add(
            Relationship(
                case_id=case_id,
                src=edge.get("source") or "",
                dst=edge.get("target") or "",
                edge_type="TRANSFER",
                amount=float(edge.get("amount") or 0),
                tx_ids=",".join(edge.get("tx_ids") or []),
            )
        )

    db.query(RiskAssessment).filter(RiskAssessment.case_id == case_id).delete()
    db.add(
        RiskAssessment(
            case_id=case_id,
            payload_json=json.dumps(result.get("risk") or {}, ensure_ascii=False),
            final_score=float((result.get("scoring") or {}).get("final") or 0),
            recommendation=v2.get("recommendation") or "",
        )
    )

    db.query(InvestigationStep).filter(InvestigationStep.case_id == case_id).delete()
    for i, s in enumerate(result.get("steps") or []):
        role = s.get("role") or ""
        db.add(
            InvestigationStep(
                case_id=case_id,
                seq=i,
                agent=role,
                title=s.get("title") or "",
                content=(s.get("content") or "")[:2000],
                prompt_version=prompt_version(role.lower()),
            )
        )


def persist_human_decision(
    db: Session,
    case_id: str,
    decision: str,
    note: str,
    recommendation: str,
    *,
    signed_by_id: str = "",
    signed_by_name: str = "",
) -> None:
    rec = db.get(AmlCase, case_id)
    if rec:
        rec.human_decision = decision
        rec.updated_at = utcnow()
        if decision == "confirm":
            if recommendation in {"CLOSE", "MONITOR"}:
                rec.status = "CLOSED"
            else:
                rec.status = "PENDING_REVIEW"
        elif decision == "reject":
            rec.status = "OPEN"
        else:
            rec.status = "PENDING_REVIEW"
    db.add(
        HumanDecision(
            case_id=case_id,
            decision=decision,
            note=note or "",
            ai_recommendation=recommendation,
            signed_by_id=signed_by_id or "",
            signed_by_name=signed_by_name or "",
        )
    )


def seed_prompt_versions(db: Session) -> None:
    from .models import PromptVersion, Regulation
    from .knowledge import _DOC_META, _article_of, list_knowledge

    for key, body in PROMPTS.items():
        if not db.get(PromptVersion, key):
            db.add(PromptVersion(id=key, body=body))
    for doc in list_knowledge():
        if db.get(Regulation, doc["id"]):
            continue
        db.add(
            Regulation(
                regulation_id=doc["id"],
                title=doc["title"],
                article=doc.get("article") or _article_of(doc),
                content=doc.get("body") or "",
                effective_date=doc.get("effective_date") or _DOC_META["effective_date"],
                expiry_date=doc.get("expiry_date") or "",
                topic=doc.get("kind") or "",
                keywords=",".join(doc.get("tags") or []),
                source=doc.get("source") or "",
                version=doc.get("version") or _DOC_META["version"],
                data_note="synthetic",
            )
        )
