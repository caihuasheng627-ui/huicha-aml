"""补证清单：规则生成签发前缺失材料，不调 LLM，不自动报送。"""

from __future__ import annotations

import re
from typing import Iterable

GENERIC_REMARKS = frozenset({"", "存入", "转出", "转账", "汇款", "备注", "无", "其他"})
PURPOSE_HINTS = ("货款", "备货", "采购", "子女", "购房", "营业收入", "咨询费", "工资", "合同", "租金", "养老金")
VOUCHER_HINTS = ("发票", "合同", "凭证", "回单", "收据")
THIN_KYC = frozenset({"缺失", "未知"})
ANON_PREFIXES = ("CASH-", "POS-")
REL_MARKERS = ("RELATIVE-", "子女", "亲属", "配偶", "父母")
UNNAMED_HINTS = ("未核名", "未知", "空壳", "未登记")
FUNNEL_TYPES = ("归集", "拆分", "快进快出")
FUNNEL_TAGS = frozenset({"mule_account", "pass_through", "layering", "structuring", "suspicious_network"})
REVIEW_BANDS = frozenset({"REPORT_REVIEW", "EDD"})
LARGE_AMT = 50_000.0
NOTE_MARK = "【补证清单】"

CATEGORIES = ("KYC", "资金用途", "关系证明", "交易凭证", "其他")
MAX_AI_GAPS = 3
_ID_LIKE = re.compile(r"^(?:EV|TX|KB|ALT|C|P|ACC)[-_][A-Z0-9][A-Z0-9._-]*$", re.I)
_BARE_CODE = re.compile(r"^[A-Z0-9._-]{6,}$", re.I)


def is_material_title(title: str) -> bool:
    text = str(title or "").strip()
    if len(text) < 4:
        return False
    if _ID_LIKE.match(text) or _BARE_CODE.match(text):
        return False
    if re.search(r"(?:EV|TX|KB)-[A-Z0-9-]{3,}", text, re.I) and not re.search(r"[\u4e00-\u9fff]", text):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def material_gap_titles(raw) -> list[str]:
    """missing_evidence 只保留中文材料名；EV/TX 编号是已调取证据，不是待补材料。"""
    seen: set[str] = set()
    out: list[str] = []
    for item in raw or []:
        title = str(item or "").strip()
        if not is_material_title(title):
            continue
        key = re.sub(r"\s+", "", title)
        if key in seen:
            continue
        seen.add(key)
        out.append(title)
        if len(out) >= MAX_AI_GAPS:
            break
    return out


def _item(
    *,
    id: str,
    title: str,
    category: str,
    reason: str,
    suggested_action: str,
    status: str,
    priority: str,
    appended: bool = False,
) -> dict:
    return {
        "id": id,
        "title": title,
        "category": category,
        "reason": reason,
        "suggested_action": suggested_action,
        "status": status,
        "priority": priority,
        "appended": appended,
    }


def _reco(ctx: dict) -> str:
    return str(ctx.get("recommendation") or "")


def _band_priority(reco: str, *, missing: bool) -> str:
    if not missing:
        return "low"
    if reco in REVIEW_BANDS:
        return "high"
    if reco == "MONITOR":
        return "medium"
    return "low"


def _opened_months(opened_at: str, alert_at: str) -> int | None:
    try:
        oy, om = int(opened_at[:4]), int(opened_at[5:7])
        ay, am = int((alert_at or opened_at)[:4]), int((alert_at or opened_at)[5:7])
        return (ay * 12 + am) - (oy * 12 + om)
    except (TypeError, ValueError, IndexError):
        return None


def _remarks(txs: list[dict]) -> list[str]:
    return [(t.get("remark") or "").strip() for t in txs]


def _is_anon_account(account_id: str) -> bool:
    return any(str(account_id or "").startswith(p) for p in ANON_PREFIXES)


def _label_unnamed(label: str) -> bool:
    text = str(label or "")
    return any(h in text for h in UNNAMED_HINTS)


def _purpose_hits(remarks: Iterable[str]) -> list[str]:
    hits = []
    for r in remarks:
        if any(h in r for h in PURPOSE_HINTS):
            hits.append(r)
    return hits


def _rel_hits(txs: list[dict], remarks: list[str]) -> bool:
    blob = " ".join(remarks)
    if any(m in blob for m in REL_MARKERS):
        return True
    return any(
        str(t.get("to_account") or "").startswith("RELATIVE-")
        or str(t.get("from_account") or "").startswith("RELATIVE-")
        for t in txs
    )


def _peers_from_graph_and_txs(graph: dict, txs: list[dict], account_id: str) -> list[dict]:
    seen: dict[str, dict] = {}
    for n in (graph or {}).get("nodes") or []:
        nid = n.get("id") or ""
        if not nid or nid == account_id or n.get("kind") == "center":
            continue
        seen[nid] = {
            "account_id": nid,
            "label": n.get("label") or nid,
            "kind": n.get("kind") or "",
            "kyc_level": n.get("kyc_level") or "",
            "name": n.get("label") or nid,
        }
    for t in txs:
        for acc in (t.get("from_account"), t.get("to_account")):
            if not acc or acc == account_id or acc in seen:
                continue
            seen[acc] = {
                "account_id": acc,
                "label": acc,
                "kind": "channel" if _is_anon_account(acc) else "counterparty",
                "kyc_level": "",
                "name": acc,
            }
    return list(seen.values())


def enrich_counterparties(db, account_id: str, txs: list[dict], graph: dict) -> list[dict]:
    """用账户→客户表补对手方 KYC；无库记录时退回图谱标签。"""
    from .tools import _customer_by_account, account_display_name

    peers = _peers_from_graph_and_txs(graph, txs, account_id)
    out = []
    for p in peers:
        acc = p["account_id"]
        row = dict(p)
        if _is_anon_account(acc) or acc.endswith("-AGG"):
            row["kyc_level"] = row.get("kyc_level") or "缺失"
            row["label"] = row.get("label") or account_display_name(db, acc)
            out.append(row)
            continue
        cust = _customer_by_account(db, acc)
        if cust:
            row["name"] = cust.name
            row["label"] = cust.name
            row["kyc_level"] = cust.kyc_level or ""
            row["customer_id"] = cust.id
            row["kind"] = cust.kind
        else:
            row["label"] = account_display_name(db, acc)
        out.append(row)
    return out


def context_from_payload(
    payload: dict,
    *,
    counterparties: list[dict] | None = None,
    human_note: str = "",
) -> dict:
    alert = payload.get("alert") or {}
    customer = payload.get("customer") or {}
    txs = payload.get("transactions") or []
    report = payload.get("report") or {}
    comparison = payload.get("comparison") or {}
    case_v2 = payload.get("case_v2") or {}
    risk = payload.get("risk") or {}
    graph = payload.get("graph") or {}
    appended = list((payload.get("checklist_appended") or {}).get("item_ids") or [])
    elements = report.get("elements") or []
    filled = comparison.get("elements_filled")
    if filled is None:
        filled = sum(1 for e in elements if str(e.get("value") or "").strip())
    reco = case_v2.get("recommendation") or risk.get("recommendation") or ""
    account_id = alert.get("account_id") or ""
    peers = counterparties if counterparties is not None else _peers_from_graph_and_txs(graph, txs, account_id)
    note = human_note or (payload.get("human_review") or {}).get("note") or ""
    return {
        "alert": alert,
        "customer": customer,
        "transactions": txs,
        "counterparties": peers,
        "recommendation": reco,
        "conclusion": payload.get("conclusion") or "",
        "alert_type": alert.get("alert_type") or "",
        "suspicious_types": case_v2.get("suspicious_types") or [],
        "elements_filled": int(filled or 0),
        "elements_total": int(comparison.get("elements_total") or len(elements) or 0),
        "can_sign": bool(payload.get("can_sign", True)),
        "appended_ids": appended,
        "human_note": note,
        "findings": payload.get("findings") or [],
    }


def _rule_counterparty_kyc(ctx: dict) -> dict:
    reco = _reco(ctx)
    peers = ctx.get("counterparties") or []
    thin = []
    for p in peers:
        acc = str(p.get("account_id") or "")
        label = str(p.get("label") or p.get("name") or acc)
        kyc = str(p.get("kyc_level") or "")
        kind = str(p.get("kind") or "")
        unnamed = _label_unnamed(label) or _is_anon_account(acc) or acc.endswith("-AGG") or kind == "channel"
        if unnamed or kyc in THIN_KYC:
            thin.append(label or acc)
    # 无对手节点但流水里有匿名渠道
    if not thin:
        for t in ctx.get("transactions") or []:
            for acc in (t.get("from_account"), t.get("to_account")):
                if _is_anon_account(str(acc or "")):
                    thin.append(str(acc))
    thin = list(dict.fromkeys(thin))
    appended = "counterparty_kyc" in set(ctx.get("appended_ids") or [])
    if thin:
        shown = "、".join(thin[:3])
        extra = f" 等 {len(thin)} 个" if len(thin) > 3 else ""
        return _item(
            id="counterparty_kyc",
            title="对手方身份核验",
            category="KYC",
            reason=f"对手方「{shown}」{extra}缺少可用 KYC（未核名、现金渠道或尽调等级为缺失）。"
            f"决策档 {reco or '未定'}，签发前应能说明对手是谁。",
            suggested_action="向客户经理或开户机构调取对手方尽调摘要，核对应受益所有人与经营地址；现金存入需柜面身份记录。",
            status="missing",
            priority=_band_priority(reco, missing=True),
            appended=appended,
        )
    if reco in REVIEW_BANDS:
        return _item(
            id="counterparty_kyc",
            title="对手方身份核验",
            category="KYC",
            reason="图谱对手已有名称，但本案建议进入上报复核，仍建议抽查受益所有人是否与登记一致。",
            suggested_action="抽查主要对手方 KYC 档案页，确认名称、证件与账户实名一致。",
            status="optional",
            priority="medium",
            appended=appended,
        )
    return _item(
        id="counterparty_kyc",
        title="对手方身份核验",
        category="KYC",
        reason="主要对手方已有登记名称，未见明显未核名或现金匿名渠道。",
        suggested_action="按行内抽查比例核对即可，不必为排除结论再等全量 KYC。",
        status="satisfied",
        priority="low",
        appended=appended,
    )


def _rule_fund_purpose(ctx: dict) -> dict:
    reco = _reco(ctx)
    remarks = _remarks(ctx.get("transactions") or [])
    hits = _purpose_hits(remarks)
    generic = [r or "（空）" for r in remarks if (r in GENERIC_REMARKS)]
    appended = "fund_purpose" in set(ctx.get("appended_ids") or [])
    if remarks and len(hits) < max(1, len(remarks) // 3):
        sample = "、".join(sorted(set(generic))[:4]) or "无备注"
        return _item(
            id="fund_purpose",
            title="资金用途说明",
            category="资金用途",
            reason=f"近窗 {len(remarks)} 笔中仅 {len(hits)} 笔备注可解释用途，其余多为「{sample}」。"
            f"无法单独用流水说明资金从哪来、到哪去。",
            suggested_action="约谈客户索取用途说明；对公补充合同/订单号，对私补充亲属关系或生活用途书面说明。",
            status="missing",
            priority=_band_priority(reco, missing=True),
            appended=appended,
        )
    if reco in REVIEW_BANDS:
        return _item(
            id="fund_purpose",
            title="资金用途说明",
            category="资金用途",
            reason="部分交易备注已含经营/生活用途，但本案建议复核上报，用途仍须与合同或发票交叉核对。",
            suggested_action="挑大额样本向客户要一份用途说明，并与备注关键词对照。",
            status="optional",
            priority="medium",
            appended=appended,
        )
    return _item(
        id="fund_purpose",
        title="资金用途说明",
        category="资金用途",
        reason=f"备注已出现「{'、'.join(sorted({h for r in hits for h in PURPOSE_HINTS if h in r})[:4])}」等可解释用途，与行业特征可对照。",
        suggested_action="排除结论下留存现有备注即可；若人工改上报，再补书面用途。",
        status="satisfied",
        priority="low",
        appended=appended,
    )


def _rule_relationship(ctx: dict) -> dict:
    reco = _reco(ctx)
    customer = ctx.get("customer") or {}
    txs = ctx.get("transactions") or []
    remarks = _remarks(txs)
    alert_type = str(ctx.get("alert_type") or "")
    tags = set(ctx.get("suspicious_types") or [])
    account_id = (ctx.get("alert") or {}).get("account_id") or ""
    appended = "relationship_proof" in set(ctx.get("appended_ids") or [])
    if _rel_hits(txs, remarks):
        return _item(
            id="relationship_proof",
            title="资金关系证明",
            category="关系证明",
            reason="流水备注或对手账户已指向登记亲属/家庭用途，关系线索可回溯。",
            suggested_action="如金额显著高于家庭常规，再补户口簿或赠与说明；否则可沿用现有登记。",
            status="satisfied",
            priority="low",
            appended=appended,
        )
    funnel = any(k in alert_type for k in FUNNEL_TYPES) or bool(tags & FUNNEL_TAGS)
    inbound = {t.get("from_account") for t in txs if t.get("to_account") == account_id}
    many_persons = len(inbound) >= 4
    individual_large = customer.get("kind") == "individual" and any(
        float(t.get("amount") or 0) >= LARGE_AMT for t in txs if t.get("from_account") == account_id
    )
    if funnel or many_persons or individual_large:
        why = []
        if funnel:
            why.append(f"告警类型/标签含归集或拆分层（{alert_type or '、'.join(sorted(tags)) or '模式命中'}）")
        if many_persons:
            why.append(f"入账对手 {len(inbound)} 个，呈多对一")
        if individual_large:
            why.append("个人户出现大额转出且未见亲属登记")
        return _item(
            id="relationship_proof",
            title="资金关系证明",
            category="关系证明",
            reason="；".join(why) + "。仅有转账关系，缺少股权、亲属或业务合同证明。",
            suggested_action="收集对手与客户的关系说明：股权/代持、亲属、上下游合同，或客户经理走访记录。",
            status="missing",
            priority=_band_priority(reco, missing=True),
            appended=appended,
        )
    if reco in REVIEW_BANDS:
        return _item(
            id="relationship_proof",
            title="资金关系证明",
            category="关系证明",
            reason="未见亲属登记，上报复核档建议补一份对手关系说明，避免只靠流水推断。",
            suggested_action="请客户书面说明与主要对手的业务或亲属关系。",
            status="optional",
            priority="medium",
            appended=appended,
        )
    return _item(
        id="relationship_proof",
        title="资金关系证明",
        category="关系证明",
        reason="未见多对一归集或个人大额无关系登记；经营对手可用现有名称解释。",
        suggested_action="排除结论下不必另补关系材料。",
        status="optional",
        priority="low",
        appended=appended,
    )


def _rule_tx_voucher(ctx: dict) -> dict:
    reco = _reco(ctx)
    txs = ctx.get("transactions") or []
    large = [t for t in txs if float(t.get("amount") or 0) >= LARGE_AMT]
    remarks = _remarks(large or txs)
    has_voucher = any(any(h in r for h in VOUCHER_HINTS) for r in remarks)
    appended = "large_tx_voucher" in set(ctx.get("appended_ids") or [])
    if has_voucher:
        return _item(
            id="large_tx_voucher",
            title="大额或可疑交易凭证",
            category="交易凭证",
            reason="大额样本备注已含发票/合同/回单类线索，可与流水交叉核对。",
            suggested_action="抽查对应凭证编号是否与交易日、金额一致。",
            status="satisfied",
            priority="low",
            appended=appended,
        )
    if large and reco in REVIEW_BANDS:
        top = max(large, key=lambda t: float(t.get("amount") or 0))
        return _item(
            id="large_tx_voucher",
            title="大额或可疑交易凭证",
            category="交易凭证",
            reason=(
                f"近窗至少 {len(large)} 笔不低于 {int(LARGE_AMT):,} 元，"
                f"最大一笔 {top.get('id') or ''} 金额 {float(top.get('amount') or 0):,.0f} 元，"
                "未见发票、合同或回单编号。上报复核前应能出示对应凭证。"
            ),
            suggested_action="向客户或柜面调取大额交易回单、合同或发票扫描件，核对日期与金额。",
            status="missing",
            priority="high",
            appended=appended,
        )
    if large:
        return _item(
            id="large_tx_voucher",
            title="大额或可疑交易凭证",
            category="交易凭证",
            reason=f"存在 {len(large)} 笔大额往来，当前结论不必立刻调原件，但归档时建议抽查回单。",
            suggested_action="按行内抽查要求复印大额回单，不必阻断排除/观察。",
            status="optional",
            priority=_band_priority(reco, missing=False) if reco == "CLOSE" else "medium",
            appended=appended,
        )
    return _item(
        id="large_tx_voucher",
        title="大额或可疑交易凭证",
        category="交易凭证",
        reason="近窗未见达到大额抽查阈值的交易，凭证不是本案缺口。",
        suggested_action="维持现有流水底稿即可。",
        status="satisfied",
        priority="low",
        appended=appended,
    )


def _rule_customer_edd(ctx: dict) -> dict:
    reco = _reco(ctx)
    customer = ctx.get("customer") or {}
    alert = ctx.get("alert") or {}
    kyc = str(customer.get("kyc_level") or "")
    summary = str(customer.get("summary") or "")
    months = _opened_months(str(customer.get("opened_at") or ""), str(alert.get("created_at") or ""))
    newish = months is not None and months < 24
    watch = bool(customer.get("watchlist"))
    thin_file = kyc in {"普通", "关注", "高风险", *THIN_KYC}
    needs_edd = reco in REVIEW_BANDS or kyc in {"关注", "高风险"} or watch or newish or "新设" in summary or "开户不足" in summary
    appended = "customer_edd" in set(ctx.get("appended_ids") or [])
    filled = int(ctx.get("elements_filled") or 0)
    total = int(ctx.get("elements_total") or 0)
    elements_gap = bool(total and filled < total)
    if (thin_file and needs_edd) or elements_gap:
        bits = []
        if kyc:
            bits.append(f"KYC 等级「{kyc}」")
        if newish and months is not None:
            bits.append(f"开户约 {months} 个月")
        if "新设" in summary or "开户不足" in summary:
            bits.append("客户摘要提示新设/新开户")
        if reco in REVIEW_BANDS:
            bits.append(f"决策档 {reco}")
        if elements_gap:
            bits.append(f"报告要素 {filled}/{total} 未写满")
        return _item(
            id="customer_edd",
            title="客户尽调档案",
            category="其他",
            reason="；".join(bits) + "。现有档案不足以支撑签发后的复核材料包。",
            suggested_action="调阅开户申请、受益所有人、经营场所与近期回访记录；关注类客户按 EDD 清单补齐。",
            status="missing",
            priority=_band_priority(reco, missing=True) if reco in REVIEW_BANDS or kyc in {"关注", "高风险"} else "medium",
            appended=appended,
        )
    if reco == "MONITOR":
        return _item(
            id="customer_edd",
            title="客户尽调档案",
            category="其他",
            reason="观察档可沿用现有客户摘要，建议在监测期满前补一次回访。",
            suggested_action="列入持续监测任务，到期补客户经理回访记录。",
            status="optional",
            priority="medium",
            appended=appended,
        )
    return _item(
        id="customer_edd",
        title="客户尽调档案",
        category="其他",
        reason=f"客户「{customer.get('name') or ''}」档案摘要可用，KYC「{kyc or '未标'}」，与排除/常规经营判断匹配。",
        suggested_action="排除结论下不必另启 EDD；若人工改上报，再调完整尽调卷。",
        status="satisfied",
        priority="low",
        appended=appended,
    )


def generate_checklist(ctx: dict) -> list[dict]:
    """给定案件/调查上下文，返回固定五条规则项（状态随案变化）。"""
    items = [
        _rule_counterparty_kyc(ctx),
        _rule_fund_purpose(ctx),
        _rule_relationship(ctx),
        _rule_tx_voucher(ctx),
        _rule_customer_edd(ctx),
    ]
    order = {"missing": 0, "optional": 1, "satisfied": 2}
    rank = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (order.get(x["status"], 9), rank.get(x["priority"], 9), x["id"]))
    return items


def attach_checklist(payload: dict, *, counterparties: list[dict] | None = None, human_note: str = "") -> dict:
    ctx = context_from_payload(payload, counterparties=counterparties, human_note=human_note)
    items = generate_checklist(ctx)
    known_titles = {str(i.get("title") or "") for i in items}
    gaps = material_gap_titles((payload.get("judge") or {}).get("missing_evidence"))
    if isinstance(payload.get("judge"), dict):
        payload["judge"]["missing_evidence"] = gaps
    for index, title in enumerate(gaps, start=1):
        if title in known_titles:
            continue
        items.append(
            _item(
                id=f"AI-GAP-{index:02d}",
                title=title,
                category="其他",
                reason="慧查agent 在支持/反向证据对照中标记该材料缺失。",
                suggested_action="由调查员核实并上传对应原始材料；不得仅凭模型描述视为已补齐。",
                status="missing",
                priority=_band_priority(ctx.get("recommendation") or "", missing=True),
            )
        )
    payload["checklist"] = summarize(items, ctx)
    return payload["checklist"]


def summarize(items: list[dict], ctx: dict) -> dict:
    missing = [i for i in items if i["status"] == "missing"]
    return {
        "items": items,
        "missing_count": len(missing),
        "optional_count": sum(1 for i in items if i["status"] == "optional"),
        "satisfied_count": sum(1 for i in items if i["status"] == "satisfied"),
        "elements_filled": ctx.get("elements_filled") or 0,
        "elements_total": ctx.get("elements_total") or 0,
        "recommendation": ctx.get("recommendation") or "",
        "note": "规则清单，不是监管结论；写入草稿备注便于人签前核对，系统不会自动报送。",
    }


def format_item_line(item: dict) -> str:
    pri = {"high": "高", "medium": "中", "low": "低"}.get(item.get("priority") or "", item.get("priority") or "")
    return f"- [{item.get('category')}/{pri}] {item.get('title')}"


def compact_item_line(line: str) -> str:
    """草稿只记待补材料名，不把规则/模型的操作建议写进底稿。"""
    text = (line or "").rstrip()
    stripped = text.strip()
    if not stripped.startswith("- ["):
        return text
    head = stripped[3:]
    end = head.find("] ")
    if end < 0:
        return text
    tag = head[:end].strip()
    title = head[end + 2 :].split("：", 1)[0].split(":", 1)[0].strip()
    if not title:
        return text
    return f"- [{tag}] {title}"


def compact_checklist_block(text: str) -> str:
    raw = text or ""
    idx = raw.find(NOTE_MARK)
    if idx < 0:
        return raw
    prefix = raw[:idx]
    lines = []
    for line in raw[idx:].splitlines():
        lines.append(compact_item_line(line) if line.startswith("- ") else line)
    return prefix + "\n".join(lines)


def _line_key(line: str) -> str:
    text = compact_item_line(line or "").strip()
    if text.startswith("- ["):
        head = text[3:]
        end = head.find("] ")
        if end >= 0:
            title = head[end + 2 :].strip()
            if title:
                return title
    return text


def merge_note(existing: str, items: list[dict]) -> str:
    raw = compact_checklist_block(existing or "")
    idx = raw.find(NOTE_MARK)
    free = raw[:idx].rstrip() if idx >= 0 else raw.strip()
    old_block = raw[idx:].strip() if idx >= 0 else ""
    by_key: dict[str, str] = {}
    for line in old_block.splitlines():
        if not line.startswith("- "):
            continue
        compact = compact_item_line(line)
        by_key[_line_key(compact)] = compact
    for it in items:
        line = format_item_line(it)
        by_key[str(it.get("title") or "").strip() or _line_key(line)] = line
    header = f"{NOTE_MARK}签发前待补材料（规则提示，非监管结论，不自动报送）"
    lines = [header, *by_key.values()] if by_key else [header]
    block = "\n".join(lines)
    if free:
        return f"{free}\n\n{block}"
    return block


def apply_remarks_to_report(report: dict, note: str, *, entries: list[dict] | None = None) -> None:
    from .notes import apply_remarks_to_report as _apply

    _apply(report, note, entries=entries)


def scrub_payload_checklist(payload: dict | None, human_note: str = "") -> tuple[dict | None, str]:
    note = compact_checklist_block(human_note or "")
    if not isinstance(payload, dict):
        return payload, note
    report = payload.get("report")
    if isinstance(report, dict) and report.get("full_text"):
        report["full_text"] = compact_checklist_block(str(report.get("full_text") or ""))
    review = payload.get("human_review")
    if isinstance(review, dict) and review.get("note"):
        review["note"] = compact_checklist_block(str(review.get("note") or ""))
    appended = payload.get("checklist_appended")
    if isinstance(appended, dict) and appended.get("text"):
        appended["text"] = compact_checklist_block(str(appended.get("text") or ""))
    return payload, note
