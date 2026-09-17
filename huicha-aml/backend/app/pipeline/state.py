from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

FAKE_ACCOUNT = "6222-FAKE-9999"


@dataclass
class RunOptions:
    use_challenger: bool = True
    inject_hallucination: bool = False
    experiment_mode: bool = False


@dataclass
class StageDeps:
    enrich_judge: Callable[..., tuple[dict, dict]]
    enrich_full_report: Callable[..., tuple[str, dict]]
    search_knowledge: Callable[..., list[dict]]


@dataclass
class StageContext:
    db: Session
    deps: StageDeps
    options: RunOptions
    emit: Callable[[dict], None] = field(default=lambda _event: None)


@dataclass
class InvestigationState:
    alert_id: str
    started: float
    tool_trace: list = field(default_factory=list)
    options: RunOptions = field(default_factory=RunOptions)
    bundle: dict = field(default_factory=dict)
    alert: dict = field(default_factory=dict)
    customer: dict = field(default_factory=dict)
    planned: list = field(default_factory=list)
    as_of: str = ""
    txs: list = field(default_factory=list)
    kb_hits: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
    account_id: str = ""
    privacy: Any = None
    analyst: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    baseline_result: dict = field(default_factory=dict)
    sampling: dict = field(default_factory=dict)
    citable: set = field(default_factory=set)
    llm_findings: list = field(default_factory=list)
    ev_graph: list = field(default_factory=list)
    allowed_evidence: list = field(default_factory=list)
    allowed_set: set = field(default_factory=set)
    prompt_allowed: list = field(default_factory=list)
    cite_set: set = field(default_factory=set)
    judge: dict = field(default_factory=dict)
    judge_validation: dict = field(default_factory=dict)
    judge_repaired: bool = False
    fallback_reason: str = ""
    judge_usage: dict = field(default_factory=dict)
    reporter_usage: dict = field(default_factory=dict)
    counterfactual: dict = field(default_factory=dict)
    evidence_sufficiency: dict = field(default_factory=dict)
    verified_claims: list = field(default_factory=list)
    agent_reliability: dict = field(default_factory=dict)
    case_facts: dict = field(default_factory=dict)
    guardrails: dict = field(default_factory=dict)
    conclusion: str = ""
    confidence: float = 0.0
    report: dict = field(default_factory=dict)
    fact_issues: list = field(default_factory=list)
    fact_retry: bool = False
    trace: list = field(default_factory=list)
    payload: dict | None = None
