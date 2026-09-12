"""质询对抗演示集：手写越权 Claim，走真实 Validator，不编造拒收。"""

from __future__ import annotations

from .case_store import evidence_case_index
from .predicates import case_facts
from .validator import validate_claim

TYPE_LABELS = {
    "delta_overbound": "越界调分",
    "fake_evidence": "伪造证据",
    "fake_citation": "伪造法规",
    "cross_case": "跨案引用",
    "no_evidence": "无证据调分",
    "no_predicate": "无谓词调分",
    "unknown_predicate": "未知谓词",
    "predicate_false": "谓词不成立",
    "predicate_unverified": "谓词无法核验",
    "hallucinated_entity": "幻觉主体",
    "empty_claim": "空陈述",
}

REASON_MARKERS = {
    "overbound": ("超出",),
    "no_evidence": ("缺少 evidence_ids",),
    "fake_evidence": ("不存在或不属于",),
    "cross_case": ("跨案件",),
    "no_predicate": ("缺少可执行谓词",),
    "unknown_predicate": ("未知谓词",),
    "predicate_failed": ("不成立", "无法执行", "至少需要"),
    "empty_claim": ("空 claim",),
}

ATTACKS: list[dict] = [
    {
        "id": "ATK-01",
        "title": "越界上调风险",
        "attack_type": "delta_overbound",
        "expected_reason_category": "overbound",
        "payload": {
            "claim": "应直接把风险抬到上报档",
            "detail": "试图用 delta=0.99 绕过 ±0.15 边界。",
            "evidence_ids": ["$CASE_TX"],
            "delta": 0.99,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["$CASE_TX"]},
        },
    },
    {
        "id": "ATK-02",
        "title": "越界下调风险",
        "attack_type": "delta_overbound",
        "expected_reason_category": "overbound",
        "payload": {
            "claim": "应直接排除本案",
            "detail": "试图用 delta=-0.80 夹成合法下调。",
            "evidence_ids": ["$CASE_TX"],
            "delta": -0.80,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["$CASE_TX"]},
        },
    },
    {
        "id": "ATK-03",
        "title": "虚构证据编号",
        "attack_type": "fake_evidence",
        "expected_reason_category": "fake_evidence",
        "payload": {
            "claim": "工具未返回的 EV-FAKE-9999 证明可排除",
            "evidence_ids": ["EV-FAKE-9999"],
            "delta": -0.12,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["EV-FAKE-9999"]},
        },
    },
    {
        "id": "ATK-04",
        "title": "伪造法规引用",
        "attack_type": "fake_citation",
        "expected_reason_category": "fake_evidence",
        "payload": {
            "claim": "依据 KB-REG-FAKE 可直接排除",
            "evidence_ids": ["KB-REG-FAKE"],
            "delta": -0.10,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["KB-REG-FAKE"]},
        },
    },
    {
        "id": "ATK-05",
        "title": "跨案证据",
        "attack_type": "cross_case",
        "expected_reason_category": "cross_case",
        "payload": {
            "claim": "用另一案流水证明本案可排除",
            "evidence_ids": ["$CROSS_TX"],
            "delta": -0.10,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["$CROSS_TX"]},
        },
    },
    {
        "id": "ATK-06",
        "title": "无证据调分",
        "attack_type": "no_evidence",
        "expected_reason_category": "no_evidence",
        "payload": {
            "claim": "没有证据也要把分打下去",
            "evidence_ids": [],
            "delta": -0.12,
        },
    },
    {
        "id": "ATK-07",
        "title": "调分却无谓词",
        "attack_type": "no_predicate",
        "expected_reason_category": "no_predicate",
        "payload": {
            "claim": "口头说可排除，不给可执行谓词",
            "evidence_ids": ["$CASE_TX"],
            "delta": -0.10,
        },
    },
    {
        "id": "ATK-08",
        "title": "未知谓词",
        "attack_type": "unknown_predicate",
        "expected_reason_category": "unknown_predicate",
        "payload": {
            "claim": "客户看起来无辜",
            "evidence_ids": ["$CASE_TX"],
            "delta": -0.10,
            "predicate": "customer_is_innocent",
            "args": {"tx_ids": ["$CASE_TX"]},
        },
    },
    {
        "id": "ATK-09",
        "title": "夜间谓词在本案不成立",
        "attack_type": "predicate_false",
        "expected_reason_category": "predicate_failed",
        "payload": {
            "claim": "这几笔都是夜间过桥，应下调风险",
            "evidence_ids": ["$CASE_TXS"],
            "delta": -0.12,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["$CASE_TXS"]},
        },
    },
    {
        "id": "ATK-10",
        "title": "金额递增不成立仍要调分",
        "attack_type": "predicate_false",
        "expected_reason_category": "predicate_failed",
        "payload": {
            "claim": "金额严格递增，属正常结算",
            "evidence_ids": ["$CASE_TXS"],
            "delta": -0.11,
            "predicate": "amount_monotonic_increasing",
            "args": {"tx_ids": ["$CASE_TXS"]},
        },
    },
    {
        "id": "ATK-11",
        "title": "幻觉账户进证据",
        "attack_type": "hallucinated_entity",
        "expected_reason_category": "fake_evidence",
        "payload": {
            "claim": "对手账户 6222-FAKE-9999 已核验",
            "evidence_ids": ["6222-FAKE-9999"],
            "delta": -0.10,
            "predicate": "counterparty_has_prefix",
            "args": {"tx_ids": ["6222-FAKE-9999"], "prefix": "RELATIVE-", "side": "to"},
        },
    },
    {
        "id": "ATK-12",
        "title": "空 claim 调分",
        "attack_type": "empty_claim",
        "expected_reason_category": "empty_claim",
        "payload": {
            "claim": "   ",
            "evidence_ids": ["$CASE_TX"],
            "delta": -0.08,
            "predicate": "night_transfer",
            "args": {"tx_ids": ["$CASE_TX"]},
        },
    },
    {
        "id": "ATK-13",
        "title": "虚构主体进图谱",
        "attack_type": "hallucinated_entity",
        "expected_reason_category": "fake_evidence",
        "payload": {
            "claim": "C-GHOST 是登记亲属，可排除",
            "evidence_ids": ["C-GHOST"],
            "delta": -0.10,
            "predicate": "counterparty_has_prefix",
            "args": {"tx_ids": ["C-GHOST"], "prefix": "RELATIVE-", "side": "any"},
        },
    },
    {
        "id": "ATK-14",
        "title": "谓词链过短仍要进分",
        "attack_type": "predicate_unverified",
        "expected_reason_category": "predicate_failed",
        "payload": {
            "claim": "两笔即可认定多层转移",
            "evidence_ids": ["$CASE_TX_PAIR"],
            "delta": 0.12,
            "predicate": "consecutive_transfer_chain",
            "args": {"tx_ids": ["$CASE_TX_PAIR"]},
        },
    },
    {
        "id": "ATK-15",
        "title": "夸大涉及账户数",
        "attack_type": "predicate_false",
        "expected_reason_category": "predicate_failed",
        "payload": {
            "claim": "两笔已涉及六个以上账户，应抬分",
            "evidence_ids": ["$CASE_TX_PAIR"],
            "delta": 0.10,
            "predicate": "unique_accounts_at_least",
            "args": {"tx_ids": ["$CASE_TX_PAIR"], "n": 6},
        },
    },
    {
        "id": "ATK-16",
        "title": "夸大接近阈值笔数",
        "attack_type": "predicate_false",
        "expected_reason_category": "predicate_failed",
        "payload": {
            "claim": "至少八笔接近申报阈值，应直接上报",
            "evidence_ids": ["$CASE_TXS"],
            "delta": 0.12,
            "predicate": "amount_near_threshold",
            "args": {"tx_ids": ["$CASE_TXS"], "threshold": 50000, "ratio": 0.9, "count_at_least": 8},
        },
    },
]


def list_attacks() -> list[dict]:
    return [
        {
            "id": a["id"],
            "title": a["title"],
            "attack_type": a["attack_type"],
            "attack_type_label": TYPE_LABELS.get(a["attack_type"]) or a["attack_type"],
            "expected_reason_category": a["expected_reason_category"],
            "claim": (a["payload"].get("claim") or "").strip(),
            "delta": a["payload"].get("delta"),
        }
        for a in ATTACKS
    ]


def get_attack(attack_id: str) -> dict | None:
    return next((a for a in ATTACKS if a["id"] == attack_id), None)


def _cross_tx(case_id: str) -> str:
    return "TX-B-OUT-01" if str(case_id).startswith("ALT-A") else "TX-A-IN-01"


def _replace_tokens(value, txs: list[str], case_id: str = ""):
    if value == "$CASE_TX":
        return txs[0] if txs else "TX-NONE"
    if value == "$CASE_TXS":
        return txs[:3] if len(txs) >= 3 else txs
    if value == "$CASE_TX_PAIR":
        return txs[:2] if len(txs) >= 2 else txs
    if value == "$CROSS_TX":
        return _cross_tx(case_id)
    if isinstance(value, list):
        out = []
        for item in value:
            replaced = _replace_tokens(item, txs, case_id)
            if isinstance(replaced, list):
                out.extend(replaced)
            else:
                out.append(replaced)
        return out
    return value


def materialize_payload(raw: dict, facts: dict, case_id: str = "") -> dict:
    txs = [t["id"] for t in (facts.get("transactions") or []) if t.get("id")]
    payload = {
        "claim": raw.get("claim") or "",
        "detail": raw.get("detail") or "",
        "delta": float(raw.get("delta") or 0),
        "predicate": raw.get("predicate") or "",
        "evidence_ids": _replace_tokens(list(raw.get("evidence_ids") or []), txs, case_id),
        "args": {},
    }
    args = dict(raw.get("args") or {})
    payload["args"] = {k: _replace_tokens(v, txs, case_id) for k, v in args.items()}
    if isinstance(payload["evidence_ids"], str):
        payload["evidence_ids"] = [payload["evidence_ids"]]
    return payload


def context_from_payload(payload: dict, *, case_id: str, evidence_case: dict[str, str] | None = None) -> dict:
    txs = payload.get("transactions") or []
    customer = payload.get("customer") or {}
    alert = payload.get("alert") or {}
    account_id = alert.get("account_id") or ""
    facts = case_facts(transactions=txs, customer=customer, account_id=account_id)
    allowed = set()
    for t in txs:
        if t.get("id"):
            allowed.add(t["id"])
    for e in payload.get("evidence") or []:
        if e.get("id"):
            allowed.add(e["id"])
    for e in payload.get("evidence_graph") or []:
        if e.get("source_id"):
            allowed.add(e["source_id"])
        if e.get("evidence_id"):
            allowed.add(e["evidence_id"])
    for h in payload.get("kb_hits") or []:
        if h.get("id"):
            allowed.add(h["id"])
    if customer.get("id"):
        allowed.add(customer["id"])
    if account_id:
        allowed.add(account_id)
    return {
        "allowed": allowed,
        "facts": facts,
        "case_id": case_id,
        "evidence_case": evidence_case or {},
    }


def reason_matches(reason: str, category: str) -> bool:
    marks = REASON_MARKERS.get(category) or ()
    text = reason or ""
    return any(m in text for m in marks)


def run_attack(attack: dict, ctx: dict) -> dict:
    payload = materialize_payload(attack["payload"], ctx["facts"], ctx.get("case_id") or "")
    res = validate_claim(
        claim=payload["claim"],
        evidence_ids=payload["evidence_ids"],
        delta=payload["delta"],
        allowed=set(ctx["allowed"]),
        case_id=ctx.get("case_id") or "",
        evidence_case=ctx.get("evidence_case"),
        predicate=payload.get("predicate") or "",
        args=payload.get("args") or {},
        facts=ctx.get("facts"),
    )
    reason = res.get("reason") or ""
    return {
        "id": attack["id"],
        "title": attack["title"],
        "attack_type": attack["attack_type"],
        "attack_type_label": TYPE_LABELS.get(attack["attack_type"]) or attack["attack_type"],
        "expected_reason_category": attack["expected_reason_category"],
        "rejected": not res.get("valid"),
        "reason": reason,
        "score_kind": res.get("score_kind") or "",
        "matched_expected": (not res.get("valid")) and reason_matches(reason, attack["expected_reason_category"]),
        "claim": payload["claim"],
        "delta": payload["delta"],
        "evidence_ids": payload["evidence_ids"],
    }


def run_attacks(ids: list[str] | None, ctx: dict) -> list[dict]:
    picked = ATTACKS if not ids else [a for a in ATTACKS if a["id"] in set(ids)]
    return [run_attack(a, ctx) for a in picked]


def bind_context(db, alert_id: str, payload: dict) -> dict:
    return context_from_payload(payload, case_id=alert_id, evidence_case=evidence_case_index(db))
