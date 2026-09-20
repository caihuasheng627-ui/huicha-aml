"""草稿备注：分条留痕、拦截快照、事实回查软提示。不改处置状态。"""

from __future__ import annotations

from .tools import fact_check

NOTE_MAX_LEN = 2000
REMARKS_MARK = "【补证备注】"
CHECKLIST_MARK = "【补证清单】"
REMARKS_DISCLAIMER = "人工声明，未经系统回查"
FINALIZED = frozenset({"confirm", "modify"})


def sanitize_note(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n").strip()
    return raw.replace(REMARKS_MARK, "补证备注").replace(CHECKLIST_MARK, "补证清单")


def split_checklist(text: str) -> tuple[str, str]:
    raw = text or ""
    idx = raw.find(CHECKLIST_MARK)
    if idx < 0:
        return raw.strip(), ""
    return raw[:idx].rstrip(), raw[idx:].strip()


def compose_human_note(existing: str, new_note: str) -> str:
    from .checklist import compact_checklist_block

    _free, checklist = split_checklist(existing)
    parts = [sanitize_note(new_note)]
    if checklist:
        parts.append(compact_checklist_block(checklist))
    return "\n\n".join(p for p in parts if p)


def snapshot_blockers(payload: dict | None) -> list[dict]:
    rows = []
    seen = set()
    for row in (payload or {}).get("sign_blockers") or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code") or "").strip() or "block"
        message = str(row.get("message") or "").strip()
        key = (code, message)
        if key in seen:
            continue
        seen.add(key)
        item = {"code": code}
        if message:
            item["message"] = message
        rows.append(item)
    return rows


def facts_from_payload(payload: dict | None) -> dict:
    data = payload or {}
    alert = data.get("alert") or {}
    customer = data.get("customer") or {}
    txs = data.get("transactions") or []
    baseline = data.get("baseline") or {}
    graph = data.get("graph") or {}
    watch = data.get("watch_hits") or []
    kb = data.get("kb_hits") or []
    amounts = {t.get("amount") for t in txs if t.get("amount") is not None}
    if alert.get("amount") is not None:
        amounts.add(alert["amount"])
    for key in (
        "sample_in_sum",
        "sample_out_sum",
        "avg_in_ticket",
        "peer_typical_monthly_in",
        "peer_typical_ticket",
    ):
        if baseline.get(key) is not None:
            amounts.add(baseline[key])
    names = {customer.get("name"), customer.get("id")}
    names.update(n.get("label") for n in (graph.get("nodes") or []) if n.get("label"))
    names.update(h.get("name") for h in watch if isinstance(h, dict) and h.get("name"))
    accounts = {alert.get("account_id")}
    for t in txs:
        accounts.add(t.get("from_account"))
        accounts.add(t.get("to_account"))
    dates = set()
    for t in txs:
        occurred = str(t.get("occurred_at") or "")
        if occurred:
            dates.add(occurred[:10])
    created = str(alert.get("created_at") or "")
    if created:
        dates.add(created[:10])
    opened = str(customer.get("opened_at") or "")
    if opened:
        dates.add(opened[:10])
    evidence_ids = [e.get("id") for e in (data.get("evidence") or []) if isinstance(e, dict) and e.get("id")]
    return {
        "amounts": sorted(a for a in amounts if a is not None),
        "tx_ids": [t["id"] for t in txs if t.get("id")],
        "accounts": sorted(a for a in accounts if a),
        "dates": sorted(d for d in dates if d),
        "names": sorted(n for n in names if n),
        "kb_ids": [h["id"] for h in kb if isinstance(h, dict) and h.get("id")],
        "ref_ids": [x for x in [alert.get("id"), *evidence_ids] if x],
    }


def check_note_facts(note: str, payload: dict | None) -> list[dict]:
    issues = fact_check(note, facts_from_payload(payload))
    for row in issues:
        row["severity"] = "soft"
    return issues


def format_remarks_section(entries: list[dict] | None, free_text: str = "") -> str:
    lines = [f"{REMARKS_MARK}（{REMARKS_DISCLAIMER}）"]
    if entries:
        for item in entries:
            who = str((item or {}).get("by_name") or "").strip()
            at = str((item or {}).get("at") or "").strip()
            text = str((item or {}).get("text") or "").strip()
            if not text:
                continue
            prefix = " ".join(part for part in (at, who) if part)
            lines.append(f"- {prefix}：{text}" if prefix else f"- {text}")
            tokens = [
                str(w.get("token") or "").strip()
                for w in (item.get("fact_warnings") or [])
                if isinstance(w, dict) and w.get("token")
            ]
            if tokens:
                lines.append(f"  系统提示：以下编号未在工具事实中出现（{'、'.join(tokens)}）")
    elif (free_text or "").strip():
        lines.append(free_text.strip())
    else:
        return ""
    return "\n".join(lines)


def _replace_section(full: str, mark: str, section: str) -> str:
    blob = (section or "").strip()
    if not blob:
        return full
    text = full or ""
    if mark in text:
        head, _sep, tail = text.partition(mark)
        nxt = tail.find("\n【")
        rest = tail[nxt:] if nxt >= 0 else ""
        return (head.rstrip() + "\n" + blob + rest).strip()
    if mark == REMARKS_MARK and CHECKLIST_MARK in text:
        head, sep, tail = text.partition(CHECKLIST_MARK)
        return (head.rstrip() + "\n" + blob + "\n" + sep + tail).strip()
    return (text.rstrip() + "\n" + blob).strip()


def apply_remarks_to_report(report: dict, note: str, *, entries: list[dict] | None = None) -> None:
    from .checklist import compact_checklist_block

    free, checklist = split_checklist(note)
    report["remarks"] = free
    full = compact_checklist_block(str(report.get("full_text") or ""))
    remarks = format_remarks_section(entries, free)
    if remarks:
        full = _replace_section(full, REMARKS_MARK, remarks)
    if checklist:
        full = _replace_section(full, CHECKLIST_MARK, compact_checklist_block(checklist))
    report["full_text"] = full


def note_metrics(pairs: list[tuple]) -> dict:
    blocked = [(inv, payload) for inv, payload in pairs if payload.get("can_sign") is False]
    sign_blocker_counts: dict[str, int] = {}
    note_by_blocker: dict[str, int] = {}
    with_note = 0
    for inv, payload in blocked:
        for row in payload.get("sign_blockers") or []:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip() or "block"
            sign_blocker_counts[code] = sign_blocker_counts.get(code, 0) + 1
        review = payload.get("human_review") or {}
        notes = [n for n in (review.get("notes") or []) if isinstance(n, dict) and (n.get("text") or "").strip()]
        free, _checklist = split_checklist(getattr(inv, "human_note", "") or "")
        if notes or free:
            with_note += 1
        for entry in notes:
            for row in entry.get("blockers") or []:
                if not isinstance(row, dict):
                    continue
                code = str(row.get("code") or "").strip() or "block"
                note_by_blocker[code] = note_by_blocker.get(code, 0) + 1
    return {
        "blocked_unsigned": len(blocked),
        "blocked_with_note": with_note,
        "blocked_note_rate": round(with_note / len(blocked), 4) if blocked else None,
        "sign_blocker_counts": sign_blocker_counts,
        "note_by_blocker": note_by_blocker,
    }
