from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


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


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), unique=True)
    payload_json: Mapped[str] = mapped_column(Text)
    conclusion: Mapped[str] = mapped_column(String)
    human_decision: Mapped[str] = mapped_column(String, default="")
    human_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
