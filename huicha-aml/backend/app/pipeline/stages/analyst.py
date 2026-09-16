from __future__ import annotations

from ...analyst_rules import analyze
from ...decision import rule_baseline
from ...evidence import build_evidence_graph, source_ids_of
from ...sampler import citable_tx_ids, compact_findings_for_llm, select_for_judge, visible_evidence_ids
from ..state import InvestigationState, StageContext


class AnalystStage:
    name = "analyst"
    role = "Analyst"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        bundle = state.bundle
        alert = state.alert
        customer = state.customer
        txs = state.txs
        kb_hits = state.kb_hits
        account_id = state.account_id
        analyst = analyze(
            alert=alert,
            customer=customer,
            txs=txs,
            account_id=account_id,
            baseline=bundle["baseline"],
            watch_hits=bundle["watch_hits"],
            graph=bundle["graph"],
        )
        findings = analyst["findings"]
        baseline_result = rule_baseline(analyst)
        sampling = select_for_judge(
            alert=alert,
            account_id=account_id,
            txs=txs,
            findings=findings,
            baseline=bundle["baseline"],
        )
        sample_txs = sampling["sample"]
        citable = citable_tx_ids(sample_txs, sampling["clusters"])
        sampling["citable_tx_ids"] = sorted(citable)
        llm_findings = compact_findings_for_llm(findings, keep_ids=citable)
        ev_graph = build_evidence_graph(alert["id"], bundle, kb_hits)
        allowed_evidence = sorted(
            source_ids_of(ev_graph)
            | {t["id"] for t in txs}
            | {customer["id"], alert["account_id"]}
            | {e for f in findings for e in f.get("evidence_ids", [])}
        )
        prompt_allowed = visible_evidence_ids(
            sample=sample_txs,
            clusters=sampling["clusters"],
            findings=llm_findings,
            extra=[customer["id"], alert["account_id"], *[h["id"] for h in kb_hits if h.get("id")]],
        )
        # 报告回查时，告警号与证据号是本案已知引用，不应被拆成数字片段误报。
        bundle["facts"]["ref_ids"] = sorted(set(bundle["facts"].get("ref_ids") or []) | {alert["id"]} | set(allowed_evidence))

        state.analyst = analyst
        state.findings = findings
        state.baseline_result = baseline_result
        state.sampling = sampling
        state.citable = citable
        state.llm_findings = llm_findings
        state.ev_graph = ev_graph
        state.allowed_evidence = allowed_evidence
        state.allowed_set = set(allowed_evidence)
        state.prompt_allowed = prompt_allowed
        state.cite_set = set(prompt_allowed)
