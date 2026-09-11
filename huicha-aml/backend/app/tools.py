from __future__ import annotations

import re

from sqlalchemy.orm import Session

from .models import Account, Alert, Customer, Transaction
from .tool_audit import tool

ALLOWED_TOOLS = [
    "get_alert",
    "get_customer",
    "get_accounts",
    "get_transactions",
    "get_related_accounts",
    "get_network",
    "get_graph",
    "get_timeline",
    "get_baseline",
    "check_watchlist",
    "search_knowledge",
    "search_regulation",
]

PEER_BASELINE = {
    "日用百货批发": {"typical_monthly_in": 2_400_000, "typical_ticket": 170_000, "note": "批发备货期单笔10–30万属常见经营区间"},
    "餐饮": {"typical_monthly_in": 800_000, "typical_ticket": 20_000, "note": "到店结算夜间入账常见"},
    "贸易代理": {"typical_monthly_in": 400_000, "typical_ticket": 80_000, "note": "新设贸易公司大额归集需审慎"},
    "个人-无固定职业": {"typical_monthly_in": 30_000, "typical_ticket": 8_000, "note": "自由职业账户少见连续接近阈值存入"},
    "个人-退休": {"typical_monthly_in": 12_000, "typical_ticket": 5_000, "note": "养老金为主，偶发亲属大额需结合用途"},
}

CANDIDATE_RE = re.compile(
    r"TX-[A-Z0-9\-]+|"
    r"6222-[A-Z0-9\-]+|"
    r"ACC-\d+|"
    r"CASH-\d+|"
    r"KB-[A-Z0-9\-]+|"
    r"(?<![A-Za-z0-9])C-[A-Z0-9]+|"
    r"\d{4}-\d{2}-\d{2}|"
    r"\d+(?:\.\d+)?\s*万元|"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|"
    r"\d{5,}"
)

REFERENCE_AMOUNTS = {50_000, 49_000, 100_000, 200_000, 300_000, 500_000, 800_000, 2_400_000}
for _peer in PEER_BASELINE.values():
    REFERENCE_AMOUNTS.add(float(_peer["typical_monthly_in"]))
    REFERENCE_AMOUNTS.add(float(_peer["typical_ticket"]))

APPROX_PREFIX_WORDS = ("约", "近", "左右", "上下", "量级", "区间", "阈值", "申报", "常见", "备货", "同业", "属")


def yuan(n) -> str:
    n = float(n)
    if abs(n) >= 10000:
        s = f" {n / 10000:.2f} 万元"
        return s.replace(" 0 万元", " 0 元").replace(".00 万元", " 万元")
    return f" {n:,.0f} 元"


def amount_known_forms(amt: float) -> set[str]:
    amt = float(amt)
    forms = {
        str(amt),
        f"{amt:.1f}",
        f"{amt:.2f}",
        f"{amt:.2f}".rstrip("0").rstrip("."),
        f"{amt:,.2f}",
        f"{amt:,.0f}",
    }
    if float(amt).is_integer():
        forms.add(str(int(amt)))
    forms.add(str(int(round(amt))))
    display = yuan(amt).strip()
    forms.add(display)
    forms.add(display.replace(" ", ""))
    if abs(amt) >= 10000:
        wan = amt / 10000
        forms.add(f"{wan:.2f}")
        forms.add(f"{wan:.1f}")
        forms.add(f"{wan:.2f}".rstrip("0").rstrip("."))
        forms.add(f"{wan:.2f} 万元")
        forms.add(f"{wan:.2f}万元")
        forms.add(f"{wan:.2f}".rstrip("0").rstrip(".") + " 万元")
        forms.add(f"{wan:.2f}".rstrip("0").rstrip(".") + "万元")
        if abs(wan - round(wan)) < 1e-9:
            forms.add(f"{int(round(wan))} 万元")
            forms.add(f"{int(round(wan))}万元")
    return {f for f in forms if f}


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
    if account_id.startswith("UNK-"):
        return "未登记对手"
    c = _customer_by_account(db, account_id)
    return c.name if c else account_id


@tool("get_alert")
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
        "gold_label": getattr(alert, "gold_label", "") or "",
    }


@tool("get_customer")
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


@tool("get_accounts")
def get_accounts(db: Session, customer_id: str) -> list[dict]:
    c = get_customer(db, customer_id)
    return [{"account_id": aid, "customer_id": customer_id} for aid in c.get("accounts") or []]


@tool("get_related_accounts")
def get_related_accounts(db: Session, account_id: str, txs: list[dict] | None = None) -> list[dict]:
    txs = txs if txs is not None else get_transactions(db, account_id)
    peers = sorted(({t["from_account"] for t in txs} | {t["to_account"] for t in txs}) - {account_id})
    return [{"account_id": p, "label": account_display_name(db, p), "edge": "TRANSFER"} for p in peers]


@tool("get_timeline")
def get_timeline(db: Session, account_id: str, txs: list[dict] | None = None) -> list[dict]:
    txs = txs if txs is not None else get_transactions(db, account_id)
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


@tool("get_network")
def get_network(db: Session, account_id: str, txs: list[dict] | None = None) -> dict:
    return get_graph(db, account_id, txs=txs)


@tool("search_regulation")
def search_regulation(query: str, as_of: str = "") -> list[dict]:
    from .knowledge import search_knowledge

    return search_knowledge(query, kind="regulation", top_k=6, as_of=as_of)


@tool("get_transactions")
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


@tool("get_baseline")
def get_baseline(
    db: Session,
    customer_id: str,
    account_id: str,
    txs: list[dict] | None = None,
    customer: dict | None = None,
) -> dict:
    customer = customer if customer is not None else get_customer(db, customer_id)
    txs = txs if txs is not None else get_transactions(db, account_id)
    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_sum = round(sum(t["amount"] for t in inflow), 2)
    out_sum = round(sum(t["amount"] for t in outflow), 2)
    avg_in = round(in_sum / max(len(inflow), 1), 2)
    peer = PEER_BASELINE.get(
        customer["industry"],
        {"typical_monthly_in": 100000, "typical_ticket": 20000, "note": "缺少同业样本，仅作演示"},
    )
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


@tool("get_graph")
def get_graph(db: Session, account_id: str, txs: list[dict] | None = None) -> dict:
    txs = txs if txs is not None else get_transactions(db, account_id)
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


@tool("check_watchlist")
def check_watchlist(db: Session, account_ids: list[str]) -> list[dict]:
    hits = []
    for aid in account_ids:
        c = _customer_by_account(db, aid)
        if c and c.watchlist:
            hits.append({"account_id": aid, "customer_id": c.id, "name": c.name})
    return hits


def peer_labels_from_graph(graph: dict, account_id: str, txs: list[dict], side: str) -> list[str]:
    node_map = {n["id"]: n.get("label") or n["id"] for n in graph.get("nodes", [])}
    labels: list[str] = []
    for t in txs:
        if side == "in" and t["to_account"] == account_id:
            raw = t["from_account"]
        elif side == "out" and t["from_account"] == account_id:
            raw = t["to_account"]
        else:
            continue
        nid = _graph_node_id(raw)
        lab = node_map.get(nid) or node_map.get(raw) or raw
        if lab not in labels:
            labels.append(lab)
    return labels


def plan_tool_names(alert_type: str) -> list[str]:
    """按告警类型选择工具子集；不再默认补齐全部工具。"""
    tools = [
        "get_alert",
        "get_customer",
        "get_accounts",
        "get_transactions",
        "get_timeline",
        "search_knowledge",
        "search_regulation",
    ]
    t = alert_type or ""
    if any(k in t for k in ("大额", "频繁", "夜间", "转账")):
        tools += ["get_baseline", "get_graph", "get_network"]
    if any(k in t for k in ("拆分", "归集", "名单", "团伙")):
        tools += ["get_graph", "get_network", "get_related_accounts", "check_watchlist"]
    if "观察" in t or "亲属" in t:
        tools += ["get_baseline", "get_graph", "get_related_accounts"]
    seen: set[str] = set()
    out: list[str] = []
    for x in tools:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _empty_baseline(customer: dict, txs: list[dict], account_id: str) -> dict:
    """未列入计划时不调用基线工具；流水合计仍可从已取交易算出。"""
    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_sum = round(sum(t["amount"] for t in inflow), 2)
    out_sum = round(sum(t["amount"] for t in outflow), 2)
    return {
        "industry": customer.get("industry", ""),
        "sample_in_count": len(inflow),
        "sample_out_count": len(outflow),
        "sample_in_sum": in_sum,
        "sample_out_sum": out_sum,
        "avg_in_ticket": round(in_sum / max(len(inflow), 1), 2),
        "peer_typical_monthly_in": 0,
        "peer_typical_ticket": 0,
        "peer_note": "本轮未调用基线工具",
        "in_sum_vs_peer": None,
        "skipped": True,
    }


def _empty_graph(account_id: str, label: str) -> dict:
    return {"nodes": [{"id": account_id, "label": label or account_id, "kind": "center"}], "edges": []}


def collect_bundle(db: Session, alert_id: str, *, tool_names: list[str] | None = None) -> dict:
    """核心取数始终执行；基线/图谱/名单仅当出现在 Planner 清单中才调用。"""
    alert = get_alert(db, alert_id)
    planned = tool_names or plan_tool_names(alert.get("alert_type") or "")
    customer = get_customer(db, alert["customer_id"])
    txs = get_transactions(db, alert["account_id"])
    if "get_baseline" in planned:
        baseline = get_baseline(db, alert["customer_id"], alert["account_id"], txs=txs, customer=customer)
    else:
        baseline = _empty_baseline(customer, txs, alert["account_id"])
    if "get_graph" in planned:
        graph = get_graph(db, alert["account_id"], txs=txs)
    else:
        graph = _empty_graph(alert["account_id"], customer.get("name") or alert["account_id"])
    if "check_watchlist" in planned:
        counter_ids = sorted({n["id"] for n in graph["nodes"] if n["id"] != alert["account_id"]})
        watch_hits = check_watchlist(db, counter_ids)
    else:
        watch_hits = []
    amounts = {
        t["amount"] for t in txs
    } | {
        alert["amount"],
        baseline["sample_in_sum"],
        baseline["sample_out_sum"],
        baseline["avg_in_ticket"],
    }
    if not baseline.get("skipped"):
        amounts |= {
            baseline["peer_typical_monthly_in"],
            baseline["peer_typical_ticket"],
        }
    name_set = {customer["name"], customer["id"]}
    name_set.update(n.get("label", "") for n in graph["nodes"] if n.get("label"))
    name_set.update(h["name"] for h in watch_hits)
    facts = {
        "amounts": sorted(amounts),
        "tx_ids": [t["id"] for t in txs],
        "accounts": sorted({alert["account_id"], *[t["from_account"] for t in txs], *[t["to_account"] for t in txs]}),
        "dates": sorted({t["occurred_at"][:10] for t in txs} | {alert["created_at"][:10], customer["opened_at"]}),
        "names": sorted(n for n in name_set if n),
    }
    return {
        "alert": alert,
        "customer": customer,
        "transactions": txs,
        "baseline": baseline,
        "graph": graph,
        "watch_hits": watch_hits,
        "facts": facts,
        "planned_tools": planned,
    }


def _wan_token_ok(token: str, known: set[str], text: str, start: int, end: int) -> bool:
    num = token.replace("万元", "").replace(",", "").strip()
    if (
        token in known
        or token.replace(" ", "") in known
        or num in known
        or f"{num} 万元" in known
        or f"{num}万元" in known
    ):
        return True
    prefix = text[max(0, start - 20) : start]
    suffix = text[end : min(len(text), end + 6)]
    if any(w in prefix for w in APPROX_PREFIX_WORDS):
        return True
    if "量级" in suffix or "左右" in suffix or "上下" in suffix:
        return True
    return False


def fact_check(text: str, facts: dict) -> list[dict]:
    """金额/账号/编号须在工具事实中；阈值与概数措辞放宽。"""
    known: set[str] = set()
    for amt in list(facts.get("amounts", [])) + list(REFERENCE_AMOUNTS):
        known.update(amount_known_forms(amt))
    for wan in (4.9, 5, 8, 10, 12, 20, 30, 80, 100, 170, 200, 240, 400, 800):
        known.update(amount_known_forms(wan * 10000))
        known.add(f"{wan} 万元")
        known.add(f"{wan}万元")
        known.add(str(wan))
        known.add(f"{wan:g}")

    known.update(facts.get("tx_ids", []))
    known.update(facts.get("accounts", []))
    known.update(facts.get("dates", []))
    known.update(facts.get("names", []))
    known.update(facts.get("kb_ids", []))

    issues = []
    seen = set()
    for m in CANDIDATE_RE.finditer(text or ""):
        token = m.group(0).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized = token.replace(",", "").replace(" ", "")
        ok = token in known or normalized in known
        if not ok and "万元" in token:
            ok = _wan_token_ok(token, known, text, m.start(), m.end())
        if not ok:
            if token.isdigit() and len(token) == 4 and token.startswith("20"):
                continue
            issues.append({"token": token, "reason": "未在工具返回值中出现"})
    return issues
