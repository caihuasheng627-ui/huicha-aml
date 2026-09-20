from __future__ import annotations

from ...tools import (
    collect_bundle,
    get_accounts,
    get_graph,
    get_related_accounts,
    get_timeline,
    get_transactions,
    search_regulation,
)
from ..state import InvestigationState, StageContext


class CollectorStage:
    name = "collector"
    role = "Collector"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        collected = _collect_stage(
            ctx.db,
            state.alert_id,
            search_knowledge=ctx.deps.search_knowledge,
            planned=state.planned or None,
        )
        state.bundle = collected["bundle"]
        state.alert = collected["alert"]
        state.customer = collected["customer"]
        state.txs = collected["txs"]
        state.kb_hits = collected["kb_hits"]
        state.planned = collected["planned"]
        state.as_of = collected["as_of"]
        state.account_id = collected["account_id"]
        state.timeline = collected["timeline"]


def _collect_stage(db, alert_id: str, *, search_knowledge, planned: list[str] | None = None) -> dict:
    bundle = collect_bundle(db, alert_id, tool_names=planned)
    alert = bundle["alert"]
    customer = bundle["customer"]
    planned = list(bundle.get("planned_tools") or planned or [])
    as_of = (alert.get("created_at") or "")[:10]
    txs = bundle["transactions"]
    account_id = alert["account_id"]
    kb_hits = search_knowledge(alert["alert_type"], customer["industry"], as_of)
    if "get_accounts" in planned:
        get_accounts(db, customer["id"])
    timeline = get_timeline(db, account_id, txs=txs) if "get_timeline" in planned else []
    if "get_related_accounts" in planned:
        peers = get_related_accounts(db, account_id, txs=txs)
        if len(peers) <= 4:
            seen = {t["id"] for t in txs}
            win = bundle.get("tx_window") or {}
            for p in peers:
                for extra in get_transactions(
                    db,
                    p["account_id"],
                    window_start=win.get("start") or "",
                    window_end=win.get("end") or "",
                ):
                    if extra["id"] not in seen:
                        extra["source"] = "peer"
                        seen.add(extra["id"])
                        txs.append(extra)
            txs.sort(key=lambda t: t.get("occurred_at") or "")
            facts = bundle.get("facts") or {}
            facts["tx_ids"] = [t["id"] for t in txs]
            facts["accounts"] = sorted(
                {account_id, *[t["from_account"] for t in txs], *[t["to_account"] for t in txs]}
            )
            facts["amounts"] = sorted(set(facts.get("amounts") or []) | {t["amount"] for t in txs})
            facts["dates"] = sorted(set(facts.get("dates") or []) | {(t.get("occurred_at") or "")[:10] for t in txs})
            bundle["facts"] = facts
            if "get_timeline" in planned:
                timeline = get_timeline(db, account_id, txs=txs)
            if "get_graph" in planned or "get_network" in planned:
                bundle["graph"] = get_graph(db, account_id, txs=txs)
    if "search_regulation" in planned:
        search_regulation(alert["alert_type"], as_of=as_of)
    bundle["facts"]["kb_ids"] = [h["id"] for h in kb_hits]
    return {
        "bundle": bundle,
        "alert": alert,
        "customer": customer,
        "planned": planned,
        "as_of": as_of,
        "txs": txs,
        "kb_hits": kb_hits,
        "timeline": timeline,
        "account_id": account_id,
    }
