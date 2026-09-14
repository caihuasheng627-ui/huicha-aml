"""确定性流水抽数：窗口全量算指标，进模只给代表样本 + 簇汇总。"""

from __future__ import annotations

from datetime import datetime

from .analyst_rules import near_threshold
from .tools import _graph_node_id

SAMPLE_CAP = 30
PEER_CAP = 4
FINDING_CAP = 3
TOP_AMOUNT = 5
NEAREST = 5
COUNTER_MIN = 2
COUNTER_MAX = 4
CLUSTER_REPS = 3


def _parse_ts(value: str) -> datetime | None:
    text = (value or "").strip().replace("T", " ")
    if not text:
        return None
    try:
        if len(text) >= 19:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        if len(text) >= 10:
            return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return None


def _hour(ts: str) -> str:
    return (ts or "")[11:13] if len(ts or "") >= 13 else ""


def _is_night(tx: dict) -> bool:
    hour = _hour(tx.get("occurred_at") or "")
    return bool(hour) and (hour >= "21" or hour < "06")


def _counterparty(tx: dict, account_id: str) -> str:
    if tx.get("to_account") == account_id:
        return str(tx.get("from_account") or "")
    if tx.get("from_account") == account_id:
        return str(tx.get("to_account") or "")
    return str(tx.get("to_account") or tx.get("from_account") or "")


def _cluster_key(tx: dict, account_id: str) -> str:
    src = _graph_node_id(tx.get("from_account") or "")
    dst = _graph_node_id(tx.get("to_account") or "")
    if tx.get("to_account") == account_id:
        return f"{src}→本账户"
    if tx.get("from_account") == account_id:
        return f"本账户→{dst}"
    return f"{src}→{dst}"


def _add_reason(reasons: dict[str, list[str]], tx_id: str, reason: str) -> None:
    bucket = reasons.setdefault(tx_id, [])
    if reason not in bucket:
        bucket.append(reason)


def _alert_match_ids(alert: dict, txs: list[dict], account_id: str) -> list[str]:
    alert_day = ((alert or {}).get("created_at") or "")[:10]
    try:
        alert_amt = float((alert or {}).get("amount") or 0)
    except (TypeError, ValueError):
        alert_amt = 0.0
    matched: list[str] = []
    seen: set[str] = set()
    for tx in txs:
        tid = tx.get("id") or ""
        if not tid or tid in seen:
            continue
        same_day = alert_day and (tx.get("occurred_at") or "")[:10] == alert_day
        same_amt = alert_amt and abs(float(tx.get("amount") or 0) - alert_amt) < 0.01
        if same_day or same_amt:
            seen.add(tid)
            matched.append(tid)
    return matched


def _build_clusters(txs: list[dict], account_id: str) -> list[dict]:
    buckets: dict[str, dict] = {}
    for tx in txs:
        key = _cluster_key(tx, account_id)
        amt = float(tx.get("amount") or 0)
        ts = tx.get("occurred_at") or ""
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "key": key,
                "count": 0,
                "sum": 0.0,
                "min": amt,
                "max": amt,
                "first_at": ts,
                "last_at": ts,
                "ids": [],
            }
            buckets[key] = bucket
        bucket["count"] += 1
        bucket["sum"] = round(bucket["sum"] + amt, 2)
        bucket["min"] = min(float(bucket["min"]), amt)
        bucket["max"] = max(float(bucket["max"]), amt)
        if ts and (not bucket["first_at"] or ts < bucket["first_at"]):
            bucket["first_at"] = ts
        if ts and (not bucket["last_at"] or ts > bucket["last_at"]):
            bucket["last_at"] = ts
        if tx.get("id"):
            bucket["ids"].append(tx["id"])

    clusters: list[dict] = []
    by_id = {tx.get("id"): tx for tx in txs if tx.get("id")}
    for key in sorted(buckets):
        bucket = buckets[key]
        rows = [by_id[i] for i in bucket["ids"] if i in by_id]
        reps: list[str] = []
        if rows:
            earliest = min(rows, key=lambda t: (t.get("occurred_at") or "", t.get("id") or ""))
            latest = max(rows, key=lambda t: (t.get("occurred_at") or "", t.get("id") or ""))
            richest = max(rows, key=lambda t: (float(t.get("amount") or 0), t.get("id") or ""))
            for cand in (earliest, richest, latest):
                cid = cand.get("id")
                if cid and cid not in reps:
                    reps.append(cid)
                if len(reps) >= CLUSTER_REPS:
                    break
        clusters.append(
            {
                "key": bucket["key"],
                "count": bucket["count"],
                "sum": bucket["sum"],
                "min": bucket["min"],
                "max": bucket["max"],
                "first_at": bucket["first_at"],
                "last_at": bucket["last_at"],
                "representative_ids": reps,
            }
        )
    return clusters


def _counter_example_ids(
    txs: list[dict],
    account_id: str,
    baseline: dict | None,
    already: set[str],
) -> list[str]:
    typical = float((baseline or {}).get("peer_typical_ticket") or 0)
    scored: list[tuple[float, str, str]] = []
    for tx in txs:
        tid = tx.get("id") or ""
        if not tid or tid in already or tx.get("source") == "peer":
            continue
        amt = float(tx.get("amount") or 0)
        if near_threshold(amt) or _is_night(tx):
            continue
        peer = _counterparty(tx, account_id)
        if peer.startswith("UNK-"):
            continue
        dist = abs(amt - typical) if typical else amt
        scored.append((dist, tx.get("occurred_at") or "", tid))
    scored.sort()
    return [tid for _, _, tid in scored[:COUNTER_MAX]]


def compact_findings_for_llm(findings: list[dict] | None, *, cap: int = 8) -> list[dict]:
    out: list[dict] = []
    for finding in findings or []:
        ids = list(finding.get("evidence_ids") or [])
        row = dict(finding)
        row["evidence_ids"] = ids[:cap]
        row["evidence_count"] = len(ids)
        out.append(row)
    return out


def visible_evidence_ids(
    *,
    sample: list[dict],
    clusters: list[dict],
    findings: list[dict],
    extra: list[str] | None = None,
) -> list[str]:
    ids: list[str] = []
    for tx in sample:
        if tx.get("id"):
            ids.append(str(tx["id"]))
    for cluster in clusters:
        ids.extend(str(i) for i in (cluster.get("representative_ids") or []) if i)
    for finding in findings:
        ids.extend(str(i) for i in (finding.get("evidence_ids") or []) if i)
    ids.extend(str(i) for i in (extra or []) if i)
    out: list[str] = []
    seen: set[str] = set()
    for item in ids:
        if not item or item.startswith("EV-") or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def select_for_judge(
    *,
    alert: dict,
    account_id: str,
    txs: list[dict],
    findings: list[dict] | None = None,
    baseline: dict | None = None,
) -> dict:
    txs = list(txs or [])
    by_id = {tx["id"]: tx for tx in txs if tx.get("id")}
    reasons: dict[str, list[str]] = {}

    alert_ids = _alert_match_ids(alert, txs, account_id)
    for tid in alert_ids:
        _add_reason(reasons, tid, "alert_match")

    finding_ids: list[str] = []
    for finding in findings or []:
        code = finding.get("code") or "finding"
        for eid in (finding.get("evidence_ids") or [])[:FINDING_CAP]:
            if eid in by_id:
                _add_reason(reasons, eid, f"finding:{code}")
                if eid not in finding_ids:
                    finding_ids.append(eid)

    subject = [tx for tx in txs if tx.get("source") != "peer" and tx.get("id")]
    top_amount = sorted(
        subject,
        key=lambda t: (-float(t.get("amount") or 0), t.get("id") or ""),
    )[:TOP_AMOUNT]
    top_ids = [tx["id"] for tx in top_amount]
    for tid in top_ids:
        _add_reason(reasons, tid, "top_amount")

    alert_ts = _parse_ts((alert or {}).get("created_at") or "")
    nearest_ids: list[str] = []
    if alert_ts:
        ranked = []
        for tx in subject:
            ts = _parse_ts(tx.get("occurred_at") or "")
            delta = abs((ts - alert_ts).total_seconds()) if ts else 10**18
            ranked.append((delta, tx.get("id") or ""))
        ranked.sort()
        nearest_ids = [tid for _, tid in ranked[:NEAREST] if tid]
        for tid in nearest_ids:
            _add_reason(reasons, tid, "nearest")

    clusters = _build_clusters(txs, account_id)
    cluster_ids: list[str] = []
    for cluster in clusters:
        for tid in cluster.get("representative_ids") or []:
            if tid in by_id:
                _add_reason(reasons, tid, "cluster_rep")
                if tid not in cluster_ids:
                    cluster_ids.append(tid)

    peer_txs = [tx for tx in txs if tx.get("source") == "peer" and tx.get("id")]
    peer_ranked = sorted(
        peer_txs,
        key=lambda t: (-float(t.get("amount") or 0), t.get("occurred_at") or "", t.get("id") or ""),
    )
    peer_ids = [tx["id"] for tx in peer_ranked[:PEER_CAP]]
    for tid in peer_ids:
        _add_reason(reasons, tid, "peer")

    selected: list[str] = []
    seen: set[str] = set()

    def take(ids: list[str], cap: int) -> None:
        for tid in ids:
            if tid not in by_id or tid in seen:
                continue
            if len(selected) >= cap:
                return
            seen.add(tid)
            selected.append(tid)

    pre_selected = set(alert_ids) | set(finding_ids) | set(top_ids) | set(nearest_ids) | set(cluster_ids)
    counter_ids = _counter_example_ids(txs, account_id, baseline, pre_selected)
    for tid in counter_ids:
        _add_reason(reasons, tid, "counter_example")
    reserve = min(COUNTER_MIN, len(counter_ids), SAMPLE_CAP)
    main_cap = SAMPLE_CAP - reserve

    take(alert_ids, main_cap)
    take(finding_ids, main_cap)
    take(top_ids, main_cap)
    take(nearest_ids, main_cap)
    take(cluster_ids, main_cap)
    take(counter_ids, SAMPLE_CAP)
    take(peer_ids, SAMPLE_CAP)

    sample = sorted(
        [by_id[tid] for tid in selected],
        key=lambda t: (t.get("occurred_at") or "", t.get("id") or ""),
    )
    sample_ids = {tx["id"] for tx in sample}
    out_reasons = {tid: reasons.get(tid) or ["selected"] for tid in sample_ids}

    inflow = [tx for tx in txs if tx.get("to_account") == account_id]
    outflow = [tx for tx in txs if tx.get("from_account") == account_id]
    summary = {
        "total": len(txs),
        "sampled": len(sample),
        "omitted": max(len(txs) - len(sample), 0),
        "in_count": len(inflow),
        "in_sum": round(sum(float(tx.get("amount") or 0) for tx in inflow), 2),
        "out_count": len(outflow),
        "out_sum": round(sum(float(tx.get("amount") or 0) for tx in outflow), 2),
        "cluster_count": len(clusters),
    }
    return {
        "sample": sample,
        "clusters": clusters,
        "summary": summary,
        "reasons": out_reasons,
    }
