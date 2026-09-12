"""V2 结构化契约。LLM / 规则输出尽量落在这些模型上，禁止只丢一段自然语言。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AMLTag = Literal[
    "structuring",
    "rapid_transfer",
    "mule_account",
    "pass_through",
    "circular_transaction",
    "layering",
    "unusual_geography",
    "unusual_frequency",
    "high_velocity",
    "suspicious_network",
    "other",
]

Disposition = Literal["exclude", "observe", "suggest_report"]
Recommendation = Literal["CLOSE", "MONITOR", "EDD", "REPORT_REVIEW"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
CaseStatus = Literal["OPEN", "INVESTIGATING", "PENDING_REVIEW", "CLOSED", "REPORTED"]
EvidenceType = Literal[
    "TRANSACTION",
    "ACCOUNT",
    "CUSTOMER",
    "RELATIONSHIP",
    "TIMELINE",
    "RULE",
    "REGULATION",
    "MODEL",
    "ANALYST",
    "COUNTER_EVIDENCE",
]


class PlanStep(BaseModel):
    step: int
    tool: str
    purpose: str
    required: bool = True


class InvestigationPlan(BaseModel):
    case_id: str
    investigation_plan: list[PlanStep]
    data_note: str = "synthetic"


class Claim(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    tag: str | None = None
    polarity: Literal["support", "counter"] = "support"
    delta: float = 0.0
    predicate: str | None = None
    args: dict = Field(default_factory=dict)


class RiskFactor(BaseModel):
    code: str
    label: str
    delta: float
    evidence_ids: list[str] = Field(default_factory=list)
    source: str = "rule"
    tag: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    evidence_ids: list[str] = Field(default_factory=list)
    support_score: float = 0.0
    score_kind: str = "id_membership"
    predicate: str | None = None
    observed: dict = Field(default_factory=dict)
    reason: str = ""
    rejected_delta: float | None = None


class JudgeRationale(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class JudgeDecision(BaseModel):
    disposition: Disposition
    confidence: float = Field(ge=0.0, le=1.0)
    typologies: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rationale: list[JudgeRationale] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class RegulationCite(BaseModel):
    regulation_id: str
    title: str
    article: str = ""
    evidence: str = ""
    source: str = ""
    as_of: str = ""


class StructuredReport(BaseModel):
    case_overview: str = ""
    customer_profile: str = ""
    transaction_summary: str = ""
    suspicious_patterns: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    counter_evidence_ids: list[str] = Field(default_factory=list)
    network_analysis: str = ""
    risk_assessment: str = ""
    challenger_review: str = ""
    regulation_basis: list[RegulationCite] = Field(default_factory=list)
    recommendation: Recommendation = "MONITOR"
    human_review: str = "须调查员签发后才可进入报送复核。Agent 不得自动上报。"
    data_note: str = "synthetic"
