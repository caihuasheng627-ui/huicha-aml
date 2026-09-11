from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # enterprise / individual
    industry: Mapped[str] = mapped_column(String)
    kyc_level: Mapped[str] = mapped_column(String)
    opened_at: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    watchlist: Mapped[int] = mapped_column(Integer, default=0)

    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    opened_at: Mapped[str] = mapped_column(String)

    customer: Mapped[Customer] = relationship(back_populates="accounts")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    from_account: Mapped[str] = mapped_column(String)
    to_account: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    occurred_at: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String)
    remark: Mapped[str] = mapped_column(String, default="")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    account_id: Mapped[str] = mapped_column(String)
    alert_type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    demo_tag: Mapped[str] = mapped_column(String, default="")  # A / B / C / filler
    upstream: Mapped[str] = mapped_column(String, default="规则引擎模拟告警")
    # 精标三档：exclude / observe / suggest_report；实验用
    gold_label: Mapped[str] = mapped_column(String, default="")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    conclusion: Mapped[str] = mapped_column(String)
    human_decision: Mapped[str] = mapped_column(String, default="")
    human_note: Mapped[str] = mapped_column(Text, default="")
    signed_by_id: Mapped[str] = mapped_column(String, default="")
    signed_by_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LlmCache(Base):
    """路演预热：同上下文 hash 命中则毫秒返回。"""

    __tablename__ = "llm_cache"

    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    response_text: Mapped[str] = mapped_column(Text)
    usage_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AmlCase(Base):
    """案件级视图：与 alerts.id 1:1，不替代告警队列。"""

    __tablename__ = "aml_cases"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    alert_id: Mapped[str] = mapped_column(String, index=True)
    customer_id: Mapped[str] = mapped_column(String, index=True)
    risk_level: Mapped[str] = mapped_column(String, default="")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="OPEN")
    investigation_status: Mapped[str] = mapped_column(String, default="")
    recommendation: Mapped[str] = mapped_column(String, default="")
    human_decision: Mapped[str] = mapped_column(String, default="")
    suspicious_types: Mapped[str] = mapped_column(String, default="")
    data_note: Mapped[str] = mapped_column(String, default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Evidence(Base):
    __tablename__ = "evidences"

    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    evidence_type: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String, default="")
    source_id: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    raw_reference: Mapped[str] = mapped_column(String, default="")
    timestamp: Mapped[str] = mapped_column(String, default="")
    reliability: Mapped[float] = mapped_column(Float, default=0.9)
    created_by: Mapped[str] = mapped_column(String, default="collector")
    polarity: Mapped[str] = mapped_column(String, default="support")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    data_note: Mapped[str] = mapped_column(String, default="synthetic")


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    src: Mapped[str] = mapped_column(String)
    dst: Mapped[str] = mapped_column(String)
    edge_type: Mapped[str] = mapped_column(String, default="TRANSFER")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    tx_ids: Mapped[str] = mapped_column(Text, default="")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class InvestigationStep(Base):
    __tablename__ = "investigation_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    agent: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    prompt_version: Mapped[str] = mapped_column(String, default="")


class HumanDecision(Base):
    __tablename__ = "human_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    decision: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(Text, default="")
    ai_recommendation: Mapped[str] = mapped_column(String, default="")
    signed_by_id: Mapped[str] = mapped_column(String, default="")
    signed_by_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Regulation(Base):
    """法规摘录表：公开要求转述，不是全文，data_note=synthetic。"""

    __tablename__ = "regulations"

    regulation_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    article: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    effective_date: Mapped[str] = mapped_column(String, default="")
    expiry_date: Mapped[str] = mapped_column(String, default="")
    topic: Mapped[str] = mapped_column(String, default="")
    keywords: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="")
    version: Mapped[str] = mapped_column(String, default="")
    data_note: Mapped[str] = mapped_column(String, default="synthetic")

