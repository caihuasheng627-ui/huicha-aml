"""从工具结果构建 Evidence Graph。禁止 LLM 创造节点。"""

from __future__ import annotations

from .tools import yuan


def build_evidence_graph(case_id: str, bundle: dict, kb_hits: list[dict]) -> list[dict]:
    alert = bundle["alert"]
    customer = bundle["customer"]
    txs = bundle["transactions"]
    graph = bundle.get("graph") or {}
    items: list[dict] = []
    n = 0

    def _add(**kwargs) -> str:
        nonlocal n
        n += 1
        eid = f"EV-{case_id}-{n:03d}"
        items.append(
            {
                "evidence_id": eid,
                "case_id": case_id,
                "created_by": "collector",
                "reliability": 0.9,
                "data_note": "synthetic",
                **kwargs,
            }
        )
        return eid

    _add(
        evidence_type="CUSTOMER",
        source_type="customer",
        source_id=customer["id"],
        description=f"{customer['name']} / {customer['industry']} / 开户 {customer['opened_at']}",
        raw_reference=customer["id"],
        polarity="support",
        timestamp=customer.get("opened_at") or "",
        metadata={"kind": customer.get("kind"), "kyc": customer.get("kyc_level")},
    )
    _add(
        evidence_type="ACCOUNT",
        source_type="account",
        source_id=alert["account_id"],
        description=f"主体账户 {alert['account_id']}",
        raw_reference=alert["account_id"],
        polarity="support",
        timestamp=alert.get("created_at") or "",
        metadata={},
    )
    for t in txs:
        _add(
            evidence_type="TRANSACTION",
            source_type="transaction",
            source_id=t["id"],
            description=(
                f"{t['occurred_at']} {t['from_account']} → {t['to_account']} "
                f"{yuan(t['amount']).strip()}（{t['channel']} {t['remark']}）"
            ),
            raw_reference=t["id"],
            polarity="support",
            timestamp=t.get("occurred_at") or "",
            metadata={"amount": t["amount"], "channel": t["channel"]},
        )
    for e in graph.get("edges") or []:
        tx_ids = [str(x) for x in (e.get("tx_ids") or []) if x]
        first_tx = tx_ids[0] if tx_ids else ""
        _add(
            evidence_type="RELATIONSHIP",
            source_type="graph_edge",
            source_id=first_tx or f"{e.get('source')}->{e.get('target')}",
            description=f"转账边 {e.get('source')} → {e.get('target')} 合计{yuan(e.get('amount') or 0).strip()} / {e.get('count') or 1}笔",
            raw_reference=",".join(tx_ids),
            polarity="support",
            timestamp="",
            metadata={"edge": "TRANSFER", "src": e.get("source"), "dst": e.get("target")},
        )
    for h in kb_hits:
        _add(
            evidence_type="REGULATION",
            source_type="knowledge",
            source_id=h["id"],
            description=f"{h.get('title','')}（{h.get('source','')}）",
            raw_reference=h["id"],
            polarity="support",
            timestamp="",
            metadata={"kind": h.get("kind")},
        )
    return items


def index_evidence(items: list[dict]) -> dict[str, dict]:
    idx = {}
    for e in items:
        idx[e["evidence_id"]] = e
        src = e.get("source_id") or ""
        if src:
            idx.setdefault(src, e)
        raw = e.get("raw_reference") or ""
        if raw:
            idx.setdefault(raw, e)
    return idx


def source_ids_of(items: list[dict]) -> set[str]:
    out: set[str] = set()
    for e in items:
        out.add(e["evidence_id"])
        if e.get("source_id"):
            out.add(e["source_id"])
        if e.get("raw_reference"):
            out.add(e["raw_reference"])
    return {x for x in out if x}


def timeline_from_txs(txs: list[dict]) -> list[dict]:
    rows = sorted(txs, key=lambda t: t.get("occurred_at") or "")
    return [
        {
            "time": t.get("occurred_at"),
            "from_account": t.get("from_account"),
            "to_account": t.get("to_account"),
            "amount": t.get("amount"),
            "channel": t.get("channel"),
            "tx_id": t.get("id"),
            "evidence_id": t.get("id"),
        }
        for t in rows
    ]
