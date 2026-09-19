"""Contest-honesty harness: full investigation agent vs direct product APIs.

Agent path: `run_investigation` / `POST /api/alerts/{id}/investigate` (planner tools,
collector extras, Judge, Skeptic/challenger, Reporter, reliability, can_sign).

Direct path: the same seeded alert, loaded with core collectors only (no planner extras,
no tool-audit context, no peer expansion), then product `rule_baseline` and a **single**
`enrich_judge` → `normalize_judge` → `verify_judge` → `apply_guardrails`.

This is a process contrast, not production F1 / accuracy. Synthetic gold and stub LLM
must not be reported as investigation quality.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .analyst_rules import analyze
from .decision import apply_guardrails, normalize_judge, rule_baseline, verify_judge
from .knowledge import retrieve_for_alert
from .llm import enrich_judge, usage_tokens
from .predicates import case_facts
from .sampler import compact_findings_for_llm, select_for_judge, visible_evidence_ids
from .tools import collect_bundle

DIRECT_CORE_TOOLS = ["get_alert", "get_customer", "get_transactions"]

CAVEAT = (
    "机制对照，不是生产准确率 / F1。"
    "合成告警 + 确定性 stub（或可选真实 API）只证明 agent 栈与直连入口在工具痕迹、"
    "Challenger/反事实、签发门禁上是否不同；不得写成调查能力分数。"
)


def load_direct_payload(db: Session, alert_id: str) -> dict:
    """Subject-account facts via product collectors, without planner extras or tool context."""
    bundle = collect_bundle(db, alert_id, tool_names=list(DIRECT_CORE_TOOLS))
    alert = bundle["alert"]
    customer = bundle["customer"]
    txs = bundle["transactions"]
    account_id = alert["account_id"]
    as_of = (alert.get("created_at") or "")[:10]
    kb_hits = retrieve_for_alert(alert.get("alert_type") or "", customer.get("industry") or "", as_of)
    analyst = analyze(
        alert=alert,
        customer=customer,
        txs=txs,
        account_id=account_id,
        baseline=bundle["baseline"],
        watch_hits=bundle["watch_hits"],
        graph=bundle["graph"],
    )
    baseline_result = rule_baseline(analyst)
    sampling = select_for_judge(
        alert=alert,
        account_id=account_id,
        txs=txs,
        findings=analyst["findings"],
        baseline=bundle["baseline"],
    )
    extra = [customer.get("id") or "", account_id, *[h.get("id") or "" for h in kb_hits]]
    prompt_allowed = visible_evidence_ids(
        sample=sampling["sample"],
        clusters=sampling["clusters"],
        findings=compact_findings_for_llm(analyst["findings"]),
        extra=extra,
    )
    return {
        "bundle": bundle,
        "alert": alert,
        "customer": customer,
        "txs": txs,
        "account_id": account_id,
        "kb_hits": kb_hits,
        "analyst": analyst,
        "baseline_result": baseline_result,
        "sampling": sampling,
        "llm_findings": compact_findings_for_llm(analyst["findings"]),
        "prompt_allowed": prompt_allowed,
        "cite_set": set(prompt_allowed),
    }


def run_direct_api(db: Session, alert_id: str) -> dict:
    """Rule baseline + one-shot product Judge. No planner / toolkit / challenger loop."""
    loaded = load_direct_payload(db, alert_id)
    baseline_result = loaded["baseline_result"]
    allowed = loaded["cite_set"]
    facts = case_facts(
        transactions=loaded["txs"],
        customer=loaded["customer"],
        account_id=loaded["account_id"],
    )
    judge: dict = {}
    verify: dict = {}
    guardrails: dict = {}
    usage: dict = {}
    error = ""
    try:
        raw, usage = enrich_judge(
            db=None,
            privacy=None,
            alert=loaded["alert"],
            customer=loaded["customer"],
            findings=loaded["llm_findings"],
            transactions=loaded["sampling"]["sample"],
            baseline=loaded["bundle"]["baseline"],
            kb_hits=loaded["kb_hits"],
            allowed_evidence=loaded["prompt_allowed"],
            tx_clusters=loaded["sampling"]["clusters"],
            tx_summary=loaded["sampling"]["summary"],
        )
        judge = normalize_judge(raw, known_ids=allowed)
        verify = verify_judge(judge, allowed_evidence=allowed, facts=facts)
        guardrails = apply_guardrails(judge, watch_hits=loaded["bundle"]["watch_hits"])
    except Exception as exc:  # noqa: BLE001 — harness must record parse/call failures
        error = str(exc)[:400]

    return {
        "entrypoint": "rule_baseline + enrich_judge (no pipeline)",
        "alert_id": alert_id,
        "use_challenger": False,
        "challenger_enabled": False,
        "rule_conclusion": baseline_result["conclusion"],
        "rule_score": baseline_result["score"],
        "rule_baseline": baseline_result,
        "judge_disposition": judge.get("disposition"),
        "judge_confidence": judge.get("confidence"),
        "conclusion": guardrails.get("final_conclusion"),
        "verify_passed": bool(verify.get("passed")) if verify else False,
        "verify_issues": list(verify.get("issues") or []) if verify else [],
        "guardrails_overridden": bool(guardrails.get("overridden")) if guardrails else False,
        "can_sign": None,
        "signing_applicable": False,
        "reliability_stance": None,
        "reliability_reason_codes": [],
        "tool_names": [],
        "tools_called": 0,
        "stages": [],
        "counterfactual_performed": False,
        "tokens": usage_tokens(usage),
        "error": error,
        "finding_codes": [f.get("code") for f in loaded["analyst"]["findings"] if f.get("code")],
        "tx_count": len(loaded["txs"]),
    }


def summarize_agent(payload: dict) -> dict:
    """Compact fields from an investigate payload (HTTP or `run_investigation`)."""
    trace = payload.get("tool_trace") or []
    stages = [row.get("role") for row in (payload.get("trace") or []) if row.get("role")]
    reliability = payload.get("agent_reliability") or {}
    cf = payload.get("counterfactual") or {}
    judge = payload.get("judge") or {}
    baseline = payload.get("rule_baseline") or {}
    llm = payload.get("llm") or {}
    usage = llm.get("usage") or {}
    return {
        "entrypoint": "POST /api/alerts/{id}/investigate",
        "alert_id": (payload.get("alert") or {}).get("id"),
        "use_challenger": bool(payload.get("use_challenger")),
        "challenger_enabled": bool((payload.get("challenger_run") or {}).get("enabled")),
        "conclusion": payload.get("conclusion"),
        "judge_disposition": judge.get("disposition"),
        "judge_confidence": judge.get("confidence"),
        "rule_conclusion": baseline.get("conclusion"),
        "rule_score": baseline.get("score"),
        "can_sign": payload.get("can_sign"),
        "signing_applicable": True,
        "reliability_stance": reliability.get("stance"),
        "reliability_reason_codes": [r.get("code") for r in (reliability.get("reasons") or []) if r.get("code")],
        "tool_names": _unique_tool_names(trace),
        "tools_called": len(trace),
        "stages": stages,
        "counterfactual_performed": bool(cf.get("performed")),
        "tokens": usage_tokens(usage) if usage else int((payload.get("comparison") or {}).get("tokens") or 0),
        "tx_count": len(payload.get("transactions") or []),
        "prompt_versions": payload.get("prompt_versions") or {},
    }


def compare_paths(db: Session, alert_id: str, *, agent_payload: dict | None = None) -> dict:
    """Run (or accept) the agent payload and the direct APIs on the same alert."""
    if agent_payload is None:
        from .agents import run_investigation

        agent_payload = run_investigation(db, alert_id, use_challenger=True, inject_hallucination=False)
    agent = summarize_agent(agent_payload)
    direct = run_direct_api(db, alert_id)
    agent_tools = set(agent["tool_names"])
    contrast = {
        "tool_traces_differ": bool(agent["tools_called"]) and direct["tools_called"] == 0,
        "agent_extra_tools": [name for name in agent["tool_names"] if name not in set(direct["tool_names"])],
        "challenger_only_on_agent": bool(agent["challenger_enabled"]) and not direct["challenger_enabled"],
        "skeptic_only_on_agent": "Skeptic" in (agent["stages"] or []) and "Skeptic" not in (direct["stages"] or []),
        "signing_gate_only_on_agent": agent["signing_applicable"] is True and direct["signing_applicable"] is False,
        "can_sign_defined_only_on_agent": agent.get("can_sign") is not None and direct.get("can_sign") is None,
        "agent_vs_rule_disagree": agent.get("conclusion") != direct.get("rule_conclusion")
        and agent.get("conclusion") is not None
        and direct.get("rule_conclusion") is not None,
        "agent_vs_direct_judge_disagree": agent.get("conclusion") != direct.get("conclusion")
        and agent.get("conclusion") is not None
        and direct.get("conclusion") is not None,
        "agent_has_get_alert": "get_alert" in agent_tools,
        "direct_has_no_planner_tools": direct["tools_called"] == 0 and not direct["stages"],
    }
    return {
        "alert_id": alert_id,
        "data_note": "synthetic",
        "caveat": CAVEAT,
        "agent": agent,
        "direct": direct,
        "contrast": contrast,
    }


def _unique_tool_names(trace: list) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for row in trace or []:
        name = str((row or {}).get("tool") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
