from sqlalchemy.orm import Session

from .models import Account, Alert, Customer, Transaction

PEER_BASELINE = {
    "日用百货批发": {"typical_monthly_in": 2_400_000, "typical_ticket": 170_000, "note": "批发备货期单笔10–30万属常见经营区间"},
    "餐饮": {"typical_monthly_in": 800_000, "typical_ticket": 20_000, "note": "到店结算夜间入账常见"},
    "贸易代理": {"typical_monthly_in": 400_000, "typical_ticket": 80_000, "note": "新设贸易公司大额归集需审慎"},
    "个人-无固定职业": {"typical_monthly_in": 30_000, "typical_ticket": 8_000, "note": "自由职业账户少见连续接近阈值存入"},
    "个人-退休": {"typical_monthly_in": 12_000, "typical_ticket": 5_000, "note": "养老金为主，偶发亲属大额需结合用途"},
}


def _customer_by_account(db: Session, account_id: str) -> Customer | None:
    acc = db.get(Account, account_id)
    if not acc:
        return None
    return db.get(Customer, acc.customer_id)


def account_display_name(db: Session, account_id: str) -> str:
    if account_id.startswith("CASH-"):
        return "现金存入"
    if account_id.startswith("POS-"):
        return "POS入账"
    if account_id.startswith("RELATIVE-"):
        return "登记亲属"
    c = _customer_by_account(db, account_id)
    return c.name if c else account_id


def get_alert(db: Session, alert_id: str) -> dict:
    alert = db.get(Alert, alert_id)
    if not alert:
        raise KeyError(alert_id)
    customer = db.get(Customer, alert.customer_id)
    return {
        "id": alert.id,
        "customer_id": alert.customer_id,
        "customer_name": customer.name if customer else "",
        "account_id": alert.account_id,
        "alert_type": alert.alert_type,
        "title": alert.title,
        "amount": alert.amount,
        "created_at": alert.created_at,
        "status": alert.status,
        "demo_tag": alert.demo_tag,
        "upstream": alert.upstream,
    }


def get_customer(db: Session, customer_id: str) -> dict:
    c = db.get(Customer, customer_id)
    if not c:
        raise KeyError(customer_id)
    accounts = db.query(Account).filter(Account.customer_id == customer_id).all()
    return {
        "id": c.id,
        "name": c.name,
        "kind": c.kind,
        "industry": c.industry,
        "kyc_level": c.kyc_level,
        "opened_at": c.opened_at,
        "city": c.city,
        "summary": c.summary,
        "watchlist": bool(c.watchlist),
        "accounts": [a.id for a in accounts],
    }


def get_transactions(db: Session, account_id: str, limit: int = 80) -> list[dict]:
    rows = (
        db.query(Transaction)
        .filter((Transaction.from_account == account_id) | (Transaction.to_account == account_id))
        .order_by(Transaction.occurred_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id,
            "from_account": t.from_account,
            "to_account": t.to_account,
            "amount": t.amount,
            "occurred_at": t.occurred_at,
            "channel": t.channel,
            "remark": t.remark,
        }
        for t in rows
    ]


def get_baseline(db: Session, customer_id: str, account_id: str) -> dict:
    customer = get_customer(db, customer_id)
    txs = get_transactions(db, account_id)
    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_sum = round(sum(t["amount"] for t in inflow), 2)
    out_sum = round(sum(t["amount"] for t in outflow), 2)
    avg_in = round(in_sum / max(len(inflow), 1), 2)
    peer = PEER_BASELINE.get(customer["industry"], {"typical_monthly_in": 100000, "typical_ticket": 20000, "note": "缺少同业样本，仅作演示"})
    return {
        "industry": customer["industry"],
        "sample_in_count": len(inflow),
        "sample_out_count": len(outflow),
        "sample_in_sum": in_sum,
        "sample_out_sum": out_sum,
        "avg_in_ticket": avg_in,
        "peer_typical_monthly_in": peer["typical_monthly_in"],
        "peer_typical_ticket": peer["typical_ticket"],
        "peer_note": peer["note"],
        "in_sum_vs_peer": round(in_sum / peer["typical_monthly_in"], 2) if peer["typical_monthly_in"] else None,
    }


def _graph_node_id(account_id: str) -> str:
    if account_id.startswith("CASH-"):
        return "CASH-AGG"
    if account_id.startswith("POS-"):
        return "POS-AGG"
    return account_id


def _ensure_graph_node(db: Session, nodes: dict, raw_id: str) -> str:
    node_id = _graph_node_id(raw_id)
    if node_id in nodes:
        return node_id
    if node_id == "CASH-AGG":
        nodes[node_id] = {"id": node_id, "label": "现金存入", "kind": "channel"}
        return node_id
    if node_id == "POS-AGG":
        nodes[node_id] = {"id": node_id, "label": "POS 入账", "kind": "channel"}
        return node_id
    other_c = _customer_by_account(db, raw_id)
    nodes[node_id] = {
        "id": node_id,
        "label": account_display_name(db, raw_id),
        "kind": "watch" if (other_c and other_c.watchlist) else "counterparty",
    }
    return node_id


def get_graph(db: Session, account_id: str) -> dict:
    txs = get_transactions(db, account_id)
    nodes = {
        account_id: {
            "id": account_id,
            "label": account_display_name(db, account_id),
            "kind": "center",
        }
    }
    buckets: dict[tuple[str, str], dict] = {}
    counts = {"CASH-AGG": 0, "POS-AGG": 0}
    for t in txs:
        src = _ensure_graph_node(db, nodes, t["from_account"])
        dst = _ensure_graph_node(db, nodes, t["to_account"])
        if src in counts:
            counts[src] += 1
        if dst in counts:
            counts[dst] += 1
        key = (src, dst)
        if key not in buckets:
            buckets[key] = {
                "id": t["id"],
                "source": src,
                "target": dst,
                "amount": 0.0,
                "count": 0,
                "tx_ids": [],
            }
        buckets[key]["amount"] = round(buckets[key]["amount"] + t["amount"], 2)
        buckets[key]["count"] += 1
        buckets[key]["tx_ids"].append(t["id"])
    if counts["CASH-AGG"] and "CASH-AGG" in nodes:
        nodes["CASH-AGG"]["label"] = f"现金存入({counts['CASH-AGG']}笔)"
    if counts["POS-AGG"] and "POS-AGG" in nodes:
        nodes["POS-AGG"]["label"] = f"POS入账({counts['POS-AGG']}笔)"
    return {"nodes": list(nodes.values()), "edges": list(buckets.values())}


def check_watchlist(db: Session, account_ids: list[str]) -> list[dict]:
    hits = []
    for aid in account_ids:
        c = _customer_by_account(db, aid)
        if c and c.watchlist:
            hits.append({"account_id": aid, "customer_id": c.id, "name": c.name})
    return hits


def collect_bundle(db: Session, alert_id: str) -> dict:
    alert = get_alert(db, alert_id)
    customer = get_customer(db, alert["customer_id"])
    txs = get_transactions(db, alert["account_id"])
    baseline = get_baseline(db, alert["customer_id"], alert["account_id"])
    graph = get_graph(db, alert["account_id"])
    counter_ids = sorted({n["id"] for n in graph["nodes"] if n["id"] != alert["account_id"]})
    watch_hits = check_watchlist(db, counter_ids)
    facts = {
        "amounts": sorted(
            {t["amount"] for t in txs}
            | {alert["amount"], baseline["sample_in_sum"], baseline["sample_out_sum"], baseline["avg_in_ticket"]}
        ),
        "tx_ids": [t["id"] for t in txs],
        "accounts": sorted({alert["account_id"], *[t["from_account"] for t in txs], *[t["to_account"] for t in txs]}),
        "dates": sorted({t["occurred_at"][:10] for t in txs} | {alert["created_at"][:10], customer["opened_at"]}),
        "names": [customer["name"], customer["id"]],
    }
    return {
        "alert": alert,
        "customer": customer,
        "transactions": txs,
        "baseline": baseline,
        "graph": graph,
        "watch_hits": watch_hits,
        "facts": facts,
    }


def fact_check(text: str, facts: dict) -> list[dict]:
    """Flag digit sequences that look like amounts/accounts but are not in tool facts."""
    import re

    issues = []
    known = set()
    for amt in facts.get("amounts", []):
        known.add(str(int(amt))) if float(amt).is_integer() else None
        known.add(str(int(round(float(amt)))))
        known.add(str(amt))
        known.add(f"{amt:.1f}")
        known.add(f"{amt:.2f}")
        known.add(f"{amt:.2f}".rstrip("0").rstrip("."))
        known.add(f"{amt:,.2f}")
    known.update(facts.get("tx_ids", []))
    known.update(facts.get("accounts", []))
    known.update(facts.get("dates", []))
    known.update(facts.get("names", []))

    candidates = re.findall(r"TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{5,}", text)
    for item in candidates:
        normalized = item.replace(",", "")
        ok = item in known or normalized in known
        if not ok:
            # allow year-like 2026
            if item.isdigit() and len(item) == 4 and item.startswith("20"):
                continue
            issues.append({"token": item, "reason": "未在工具返回值中出现"})
    return issues
