"""可执行 Claim 谓词：Challenger 只能从封闭集合选题，由确定性代码对案件快照复核真假。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

NEAR_THRESHOLD = 50_000.0
NEAR_RATIO = 0.9
ALLOWED_WINDOWS = frozenset({15, 30, 60, 120, 180, 360})
ALLOWED_PREFIXES = frozenset({"RELATIVE-", "UNK-", "CASH-", "POS-"})
ALLOWED_SIDES = frozenset({"from", "to", "any"})
ALLOWED_COUNT_AT_LEAST = frozenset({1, 3, 5, 8})
ALLOWED_HOP_N = frozenset({3, 4, 5, 6})

PredicateFn = Callable[[dict, dict], dict]


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out


def _parse_dt(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    return None


def _tx_index(facts: dict) -> dict[str, dict]:
    return {str(t.get("id")): t for t in (facts.get("transactions") or []) if t.get("id")}


def _load_txs(facts: dict, tx_ids: list[str]) -> tuple[list[dict] | None, str]:
    ids = _as_str_list(tx_ids)
    if not ids:
        return None, "缺少 tx_ids"
    index = _tx_index(facts)
    missing = [i for i in ids if i not in index]
    if missing:
        return None, f"交易不在本案快照：{','.join(missing[:6])}"
    rows = [index[i] for i in ids]
    rows.sort(key=lambda t: (t.get("occurred_at") or "", t.get("id") or ""))
    return rows, ""


def _fail(reason: str, *, observed: dict | None = None) -> dict:
    return {"ok": False, "true": False, "reason": reason, "observed": observed or {}}


def _ok(true: bool, reason: str, observed: dict) -> dict:
    return {"ok": True, "true": true, "reason": reason, "observed": observed}


def _near_threshold(amount: float, threshold: float = NEAR_THRESHOLD, ratio: float = NEAR_RATIO) -> bool:
    return threshold * ratio <= float(amount) < threshold


def _night(ts: str) -> bool:
    dt = _parse_dt(ts)
    if not dt:
        return False
    return dt.hour >= 21 or dt.hour < 6


def pred_amount_monotonic_decreasing(facts: dict, args: dict) -> dict:
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if len(rows) < 3:
        return _fail("amount_monotonic_decreasing 至少需要 3 笔交易")
    amounts = [float(t["amount"]) for t in rows]
    true = all(a > b for a, b in zip(amounts, amounts[1:]))
    return _ok(
        true,
        "按时间金额严格递减" if true else "按时间金额并非严格递减",
        {"tx_ids": [t["id"] for t in rows], "amounts": amounts},
    )


def pred_amount_monotonic_increasing(facts: dict, args: dict) -> dict:
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if len(rows) < 3:
        return _fail("amount_monotonic_increasing 至少需要 3 笔交易")
    amounts = [float(t["amount"]) for t in rows]
    true = all(a < b for a, b in zip(amounts, amounts[1:]))
    return _ok(
        true,
        "按时间金额严格递增" if true else "按时间金额并非严格递增",
        {"tx_ids": [t["id"] for t in rows], "amounts": amounts},
    )


def pred_consecutive_transfer_chain(facts: dict, args: dict) -> dict:
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if len(rows) < 3:
        return _fail("consecutive_transfer_chain 至少需要 3 笔交易")
    hops = [(t["from_account"], t["to_account"]) for t in rows]
    true = all(hops[i][1] == hops[i + 1][0] for i in range(len(hops) - 1))
    path = " → ".join([hops[0][0], *[h[1] for h in hops]])
    return _ok(
        true,
        f"连续过桥 {path}" if true else "交易未形成连续过桥链",
        {"tx_ids": [t["id"] for t in rows], "path": path},
    )


def pred_within_time_window_minutes(facts: dict, args: dict) -> dict:
    try:
        minutes = int(args.get("minutes"))
    except (TypeError, ValueError):
        return _fail("minutes 必须是整数")
    if minutes not in ALLOWED_WINDOWS:
        return _fail(f"minutes 不在允许集合 {sorted(ALLOWED_WINDOWS)}")
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if len(rows) < 2:
        return _fail("within_time_window_minutes 至少需要 2 笔交易")
    dts = [_parse_dt(t.get("occurred_at") or "") for t in rows]
    if any(d is None for d in dts):
        return _fail("存在无法解析的交易时间")
    span = (max(dts) - min(dts)).total_seconds() / 60.0  # type: ignore[operator]
    true = span <= minutes + 1e-9
    return _ok(
        true,
        f"首末间隔 {span:.1f} 分钟 ≤ {minutes}" if true else f"首末间隔 {span:.1f} 分钟超过 {minutes}",
        {"tx_ids": [t["id"] for t in rows], "span_minutes": round(span, 2), "minutes": minutes},
    )


def pred_amount_near_threshold(facts: dict, args: dict) -> dict:
    threshold = float(args.get("threshold") if args.get("threshold") is not None else NEAR_THRESHOLD)
    ratio = float(args.get("ratio") if args.get("ratio") is not None else NEAR_RATIO)
    if abs(threshold - NEAR_THRESHOLD) > 1e-9 or abs(ratio - NEAR_RATIO) > 1e-9:
        return _fail("threshold/ratio 必须为 50000 / 0.9")
    try:
        need = int(args.get("count_at_least") if args.get("count_at_least") is not None else 1)
    except (TypeError, ValueError):
        return _fail("count_at_least 必须是整数")
    if need not in ALLOWED_COUNT_AT_LEAST:
        return _fail(f"count_at_least 不在允许集合 {sorted(ALLOWED_COUNT_AT_LEAST)}")
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    hits = [t["id"] for t in rows if _near_threshold(t["amount"], threshold, ratio)]
    true = len(hits) >= need
    return _ok(
        true,
        f"{len(hits)} 笔接近 {int(threshold)} 元阈值（需 ≥{need}）",
        {"tx_ids": [t["id"] for t in rows], "hit_ids": hits, "count_at_least": need},
    )


def pred_counterparty_has_prefix(facts: dict, args: dict) -> dict:
    prefix = str(args.get("prefix") or "").strip()
    side = str(args.get("side") or "any").strip() or "any"
    if prefix not in ALLOWED_PREFIXES:
        return _fail(f"prefix 不在允许集合 {sorted(ALLOWED_PREFIXES)}")
    if side not in ALLOWED_SIDES:
        return _fail("side 必须是 from / to / any")
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if not rows:
        return _fail("缺少交易")

    def hit(t: dict) -> bool:
        frm, to = str(t.get("from_account") or ""), str(t.get("to_account") or "")
        if side == "from":
            return frm.startswith(prefix)
        if side == "to":
            return to.startswith(prefix)
        return frm.startswith(prefix) or to.startswith(prefix)

    matched = [t["id"] for t in rows if hit(t)]
    true = len(matched) == len(rows)
    return _ok(
        true,
        f"全部对手带前缀 {prefix}" if true else f"并非全部对手带前缀 {prefix}",
        {"tx_ids": [t["id"] for t in rows], "prefix": prefix, "side": side, "matched": matched},
    )


def pred_night_transfer(facts: dict, args: dict) -> dict:
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if not rows:
        return _fail("缺少交易")
    matched = [t["id"] for t in rows if _night(t.get("occurred_at") or "")]
    true = len(matched) == len(rows)
    return _ok(
        true,
        "所列交易均在 21:00–06:00" if true else "所列交易并非均在夜间",
        {"tx_ids": [t["id"] for t in rows], "matched": matched},
    )


def pred_all_same_channel(facts: dict, args: dict) -> dict:
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if len(rows) < 2:
        return _fail("all_same_channel 至少需要 2 笔交易")
    channels = [str(t.get("channel") or "") for t in rows]
    true = bool(channels[0]) and all(c == channels[0] for c in channels)
    return _ok(
        true,
        f"渠道均为 {channels[0]}" if true else "渠道不一致",
        {"tx_ids": [t["id"] for t in rows], "channels": channels},
    )


def pred_unique_accounts_at_least(facts: dict, args: dict) -> dict:
    try:
        n = int(args.get("n"))
    except (TypeError, ValueError):
        return _fail("n 必须是整数")
    if n not in ALLOWED_HOP_N:
        return _fail(f"n 不在允许集合 {sorted(ALLOWED_HOP_N)}")
    rows, err = _load_txs(facts, args.get("tx_ids") or [])
    if err:
        return _fail(err)
    if len(rows) < 2:
        return _fail("unique_accounts_at_least 至少需要 2 笔交易")
    accounts = sorted({str(t.get("from_account") or "") for t in rows} | {str(t.get("to_account") or "") for t in rows} - {""})
    true = len(accounts) >= n
    return _ok(
        true,
        f"涉及 {len(accounts)} 个账户（需 ≥{n}）",
        {"tx_ids": [t["id"] for t in rows], "accounts": accounts, "n": n},
    )


PREDICATES: dict[str, dict[str, Any]] = {
    "amount_monotonic_decreasing": {
        "fn": pred_amount_monotonic_decreasing,
        "label": "金额按时间严格递减",
        "args": "tx_ids（≥3）",
    },
    "amount_monotonic_increasing": {
        "fn": pred_amount_monotonic_increasing,
        "label": "金额按时间严格递增",
        "args": "tx_ids（≥3）",
    },
    "consecutive_transfer_chain": {
        "fn": pred_consecutive_transfer_chain,
        "label": "连续过桥 A→B→C",
        "args": "tx_ids（≥3）",
    },
    "within_time_window_minutes": {
        "fn": pred_within_time_window_minutes,
        "label": "首末交易落在有界时间窗",
        "args": "tx_ids（≥2），minutes∈{15,30,60,120,180,360}",
    },
    "amount_near_threshold": {
        "fn": pred_amount_near_threshold,
        "label": "接近大额申报阈值",
        "args": "tx_ids，threshold=50000，ratio=0.9，count_at_least∈{1,3,5,8}",
    },
    "counterparty_has_prefix": {
        "fn": pred_counterparty_has_prefix,
        "label": "对手账号带类型学前缀",
        "args": "tx_ids，prefix∈{RELATIVE-,UNK-,CASH-,POS-}，side∈{from,to,any}",
    },
    "night_transfer": {
        "fn": pred_night_transfer,
        "label": "夜间交易（21:00–06:00）",
        "args": "tx_ids",
    },
    "all_same_channel": {
        "fn": pred_all_same_channel,
        "label": "渠道一致",
        "args": "tx_ids（≥2）",
    },
    "unique_accounts_at_least": {
        "fn": pred_unique_accounts_at_least,
        "label": "涉及账户数达到下限",
        "args": "tx_ids（≥2），n∈{3,4,5,6}",
    },
}


def catalog_for_prompt() -> list[dict]:
    return [{"name": name, "label": spec["label"], "args": spec["args"]} for name, spec in PREDICATES.items()]


def case_facts(*, transactions: list[dict] | None, customer: dict | None = None, account_id: str = "") -> dict:
    compact = []
    for t in transactions or []:
        compact.append(
            {
                "id": t.get("id"),
                "from_account": t.get("from_account"),
                "to_account": t.get("to_account"),
                "amount": t.get("amount"),
                "occurred_at": t.get("occurred_at"),
                "channel": t.get("channel"),
                "remark": t.get("remark"),
            }
        )
    return {"transactions": compact, "customer": customer or {}, "account_id": account_id}


def execute_predicate(name: str, args: dict | None, facts: dict | None) -> dict:
    key = str(name or "").strip()
    if not key:
        return _fail("缺少 predicate")
    spec = PREDICATES.get(key)
    if not spec:
        return _fail(f"未知谓词：{key}")
    if facts is None:
        return _fail("无法执行谓词：缺少案件事实快照")
    payload = args if isinstance(args, dict) else {}
    try:
        result = spec["fn"](facts, payload)
    except (TypeError, ValueError, KeyError) as e:
        return _fail(f"谓词执行异常：{e}")
    result["predicate"] = key
    return result


def pick_true_predicate(facts: dict, allowed_ids: set[str] | None = None) -> dict | None:
    """给 stub / 单测挑一条对本案为真的谓词，避免固定 delta 在无法核验时偷偷进分。"""
    allowed = set(allowed_ids or [])
    txs = [t for t in (facts.get("transactions") or []) if t.get("id")]
    if allowed:
        txs = [t for t in txs if t["id"] in allowed]
    txs = sorted(txs, key=lambda t: (t.get("occurred_at") or "", t.get("id") or ""))
    if not txs:
        return None
    ids = [t["id"] for t in txs]

    candidates: list[tuple[str, dict]] = []
    if len(ids) >= 3:
        candidates.append(("consecutive_transfer_chain", {"tx_ids": ids[:6]}))
        candidates.append(("amount_monotonic_decreasing", {"tx_ids": ids[:6]}))
        candidates.append(("amount_monotonic_increasing", {"tx_ids": ids[:6]}))
    near = [t["id"] for t in txs if _near_threshold(t["amount"])]
    if len(near) >= 8:
        candidates.append(("amount_near_threshold", {"tx_ids": near[:12], "count_at_least": 8}))
    elif len(near) >= 3:
        candidates.append(("amount_near_threshold", {"tx_ids": near[:8], "count_at_least": 3}))
    elif near:
        candidates.append(("amount_near_threshold", {"tx_ids": near[:3], "count_at_least": 1}))
    for prefix in ("UNK-", "RELATIVE-", "CASH-", "POS-"):
        hits = [
            t["id"]
            for t in txs
            if str(t.get("from_account") or "").startswith(prefix) or str(t.get("to_account") or "").startswith(prefix)
        ]
        if hits:
            candidates.append(("counterparty_has_prefix", {"tx_ids": hits[:6], "prefix": prefix, "side": "any"}))
    night = [t["id"] for t in txs if _night(t.get("occurred_at") or "")]
    if night:
        candidates.append(("night_transfer", {"tx_ids": night[:4]}))
    if len(ids) >= 2:
        candidates.append(("unique_accounts_at_least", {"tx_ids": ids[:8], "n": 3}))
        candidates.append(("within_time_window_minutes", {"tx_ids": ids[:4], "minutes": 360}))
        candidates.append(("all_same_channel", {"tx_ids": ids[:4]}))

    for name, args in candidates:
        result = execute_predicate(name, args, facts)
        if result.get("ok") and result.get("true"):
            return {"predicate": name, "args": args, "evidence_ids": list(args.get("tx_ids") or [])}
    return None


def stub_challenger_item(
    context: dict,
    *,
    claim: str,
    detail: str,
    delta: float,
) -> dict:
    facts = case_facts(
        transactions=context.get("transactions") or [],
        customer=context.get("customer") or {},
        account_id=str((context.get("alert") or {}).get("account_id") or ""),
    )
    allowed = set(context.get("allowed_evidence_ids") or [])
    tx_ids = {t.get("id") for t in facts.get("transactions") or [] if t.get("id")}
    scope = (allowed & tx_ids) or tx_ids
    picked = pick_true_predicate(facts, scope)
    if not picked:
        return {
            "claim": claim,
            "detail": detail,
            "evidence_ids": list(allowed)[:2],
            "delta": delta,
        }
    return {
        "claim": claim,
        "detail": f"{detail} 谓词 {picked['predicate']} 须经数据复核。",
        "evidence_ids": picked["evidence_ids"],
        "predicate": picked["predicate"],
        "args": picked["args"],
        "delta": delta,
    }
