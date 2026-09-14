from __future__ import annotations

import re
from functools import lru_cache

# 本地制度/类型学摘录：公开要求的转述，不是法规全文，供 Agent 检索引用。
DOCUMENTS: list[dict] = [
    {
        "id": "KB-REG-01",
        "kind": "regulation",
        "title": "可疑交易须人工分析并记录过程",
        "source": "《金融机构大额交易和可疑交易报告管理办法》第十四条（转述）",
        "tags": ["人工分析", "过程记录", "可疑交易", "调查", "报告"],
        "body": "金融机构发现或者有合理理由怀疑客户、客户的资金或者其他资产与洗钱等犯罪活动有关的，应当提交可疑交易报告。报告前须开展人工分析，并把分析过程留下来，不能只靠系统自动出数交差。",
    },
    {
        "id": "KB-REG-02",
        "kind": "regulation",
        "title": "排除告警须记录合理理由",
        "source": "人民银行关于执行可疑交易报告工作的要求（转述）",
        "tags": ["排除", "理由", "误报", "关闭", "批发", "经营"],
        "body": "监测系统命中后，若经调查认为不构成可疑，仍须写下合理排除理由，例如交易与客户身份、职业或经营特征相符。不能只点关闭、不留痕迹。",
    },
    {
        "id": "KB-REG-03",
        "kind": "regulation",
        "title": "可疑交易报告核心要素",
        "source": "管理办法及监测中心要素规范（转述）",
        "tags": ["报告要素", "资金交易", "客户行为", "疑点分析", "理由", "STR"],
        "body": "草稿至少覆盖：报告触发点；资金交易及客户行为；疑点分析；可疑或排除理由。身份、交易、行为特征要能对上证据，要素不全或错误可能被要求补正。",
    },
    {
        "id": "KB-REG-04",
        "kind": "regulation",
        "title": "要素不全须限期补正",
        "source": "人民银行关于可疑交易报告补正时限的执行要求（转述）",
        "tags": ["补正", "五日", "要素", "质量"],
        "body": "监测中心认为要素不全或填写错误的，可退回补正。机构一般应在五个工作日内补正。调查工作台的价值是先把要素和证据编号写全，降低补正。",
        # 条款级生效日晚于库默认值：案发日早于此日时不应被引用。
        "effective_date": "2021-03-01",
        "version": "paraphrase-v1-corr-2021",
    },
    {
        "id": "KB-REG-05",
        "kind": "regulation",
        "title": "上报前须审定，不得系统自动直报",
        "source": "管理办法第二十七条、第二十八条（转述）",
        "tags": ["审定", "签发", "人工", "自动报送", "总部"],
        "body": "分析应至少经过初审和复核，上报前由总部专门机构审定。Agent 只出草稿，不能写核心、不能自动提交监测中心，结论须调查员签发。",
    },
    {
        "id": "KB-TYP-01",
        "kind": "typology",
        "title": "拆分存入以规避大额阈值",
        "source": "调查类型学（演示库）",
        "tags": ["拆分", "structuring", "阈值", "现金", "存入", "4.9万", "5万"],
        "body": "多笔流入金额落在大额申报阈值稍下方，随后集中转出，是常见拆分手法。需结合职业、存入渠道和转出时间判断，不能单看一笔刚低于阈值。",
    },
    {
        "id": "KB-TYP-02",
        "kind": "typology",
        "title": "多个个人账户向新设企业归集",
        "source": "调查类型学（演示库）",
        "tags": ["归集", "多账户", "新设", "贸易", "漏斗", "对手方"],
        "body": "开户不久的贸易公司短期内接收多个个人账户转入，再快速外转或支付咨询费，需核验真实贸易背景。对手方若命中关注名单，应提高上报倾向。",
    },
    {
        "id": "KB-TYP-03",
        "kind": "typology",
        "title": "夜间快进快出",
        "source": "调查类型学（演示库）",
        "tags": ["夜间", "快进快出", "转出", "网银"],
        "body": "日间拆分或归集完成后，在 21 时后集中转出，削弱经营结算解释。餐饮等业态夜间入账需与此区分，看对手方是否为收银/POS 而非个人现金。",
    },
    {
        "id": "KB-TYP-04",
        "kind": "typology",
        "title": "批发备货导致的大额频繁误报",
        "source": "调查类型学（演示库）",
        "tags": ["大额频繁", "批发", "备货", "误报", "上下游"],
        "body": "日用百货批发在换季备货期会出现对公大额进出。若对手方为稳定上下游、KYC 非高风险、规模落在同业区间，优先考虑经营性解释，由质疑角色回写排除理由。",
    },
    {
        "id": "KB-IND-01",
        "kind": "industry",
        "title": "日用百货批发行为基线",
        "source": "同业行为基线（演示库）",
        "tags": ["日用百货批发", "批发", "对公", "备货", "便利店"],
        "body": "批发备货期单笔 10–30 万属常见经营区间；下游便利店/商超反复入账、上游供应中心反复出账，不等于拆分。月度流入量级可到数百万元。",
    },
    {
        "id": "KB-IND-02",
        "kind": "industry",
        "title": "无固定职业个人账户",
        "source": "同业行为基线（演示库）",
        "tags": ["个人-无固定职业", "自由职业", "现金", "拆分"],
        "body": "自由职业账户少见连续接近阈值的现金存入。开户时间短、对手分散后突然收口并夜间转出，经营解释通常不足。",
    },
    {
        "id": "KB-IND-03",
        "kind": "industry",
        "title": "新设贸易代理",
        "source": "同业行为基线（演示库）",
        "tags": ["贸易代理", "新设", "归集", "注册资本"],
        "body": "新设贸易公司大额归集需审慎：核对合同、物流和受益所有人。注册资本低、KYC 为关注级时，不能仅凭「货款」备注排除。",
    },
    {
        "id": "KB-IND-04",
        "kind": "industry",
        "title": "餐饮结算夜间入账",
        "source": "同业行为基线（演示库）",
        "tags": ["餐饮", "夜间", "POS", "营业收入"],
        "body": "到店结算夜间入账常见，POS/收银高峰出现在 21 时后不构成拆分。对手方应为收单通道而非多个陌生个人。",
    },
    {
        "id": "KB-IND-05",
        "kind": "industry",
        "title": "退休客户偶发大额",
        "source": "同业行为基线（演示库）",
        "tags": ["个人-退休", "养老金", "亲属", "购房"],
        "body": "养老金为主的账户，偶发亲属大额需结合用途。柜面转给已登记亲属并注明购房的，可在核验关系后排除或继续观察，不宜直接当团伙归集。",
    },
    {
        "id": "KB-TYP-05",
        "kind": "typology",
        "title": "短时多层过桥转账",
        "source": "调查类型学（演示库）",
        "tags": ["多层", "layering", "过桥", "快进快出", "pass_through"],
        "body": "资金在短时间内经 A→B→C→D 多层账户递减转出，需核验贸易/工资解释。单看一笔对公转账不足以定层。本条为演示摘录。",
    },
    {
        "id": "KB-PROC-01",
        "kind": "process",
        "title": "质疑复核抑制确认偏误",
        "source": "调查作业手册（演示库）",
        "tags": ["质疑", "Challenger", "确认偏误", "反证"],
        "body": "Analyst 先列疑点，Challenger 必须尝试经营或用途抗辩。关掉质疑后，批发类误报更容易被建议上报。结论不得用案例标签锁死。",
    },
]


_KIND_LABEL = {
    "regulation": "监管要素",
    "typology": "调查类型学",
    "industry": "行业基线",
    "process": "作业规程",
}

# 摘录不是现行有效法规全文。effective/expiry 用于「案发日是否适用」演示。
# 全局值为缺省回退；DOCUMENTS 条目可覆盖条款级日期/版本。
_DOC_META = {
    "effective_date": "2017-01-01",
    "expiry_date": None,
    "version": "paraphrase-v1",
    "source_note": "公开要求转述，非法规全文，synthetic/demo",
}


def _article_of(doc: dict) -> str:
    src = doc.get("source") or ""
    m = re.search(r"第[一二三四五六七八九十百零0-9]+条", src)
    return m.group(0) if m else ""


def _meta_of(doc: dict) -> dict:
    """条款级字段优先，缺省回退到全局 _DOC_META。"""
    return {
        "effective_date": doc.get("effective_date") or _DOC_META["effective_date"],
        "expiry_date": doc["expiry_date"] if "expiry_date" in doc else _DOC_META["expiry_date"],
        "version": doc.get("version") or _DOC_META["version"],
        "source_note": doc.get("source_note") or _DOC_META["source_note"],
    }


def _applicable(doc: dict, as_of: str) -> bool:
    if not as_of:
        return True
    meta = _meta_of(doc)
    start = meta["effective_date"]
    end = meta["expiry_date"]
    if start and as_of < start:
        return False
    if end and as_of > end:
        return False
    return True


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    parts = [p for p in re.split(r"[\s,，。；、/（）()「」【】：:]+", text) if len(p) >= 2]
    hans = re.findall(r"[\u4e00-\u9fff]+", text)
    extra: list[str] = []
    for h in hans:
        extra.append(h)
        if len(h) >= 4:
            extra.extend(h[i : i + 2] for i in range(len(h) - 1))
    ascii_words = re.findall(r"[a-z0-9\-]{3,}", text)
    return {t for t in [*parts, *extra, *ascii_words] if t}


@lru_cache(maxsize=1)
def _indexed() -> list[dict]:
    out = []
    for doc in DOCUMENTS:
        blob = " ".join([doc["id"], doc["title"], doc["body"], " ".join(doc["tags"])])
        out.append({**doc, "_tokens": _tokens(blob)})
    return out


def corpus_size() -> int:
    return len(DOCUMENTS)


def list_knowledge() -> list[dict]:
    out = []
    for d in DOCUMENTS:
        meta = _meta_of(d)
        out.append(
            {
                "id": d["id"],
                "kind": d["kind"],
                "kind_label": _KIND_LABEL.get(d["kind"], d["kind"]),
                "title": d["title"],
                "source": d["source"],
                "tags": d["tags"],
                "body": d["body"],
                "article": _article_of(d),
                "effective_date": meta["effective_date"],
                "expiry_date": meta["expiry_date"],
                "version": meta["version"],
                "data_note": "synthetic-paraphrase",
            }
        )
    return out


def search_knowledge(query: str, *, kind: str | None = None, top_k: int = 4, as_of: str = "") -> list[dict]:
    q_tokens = _tokens(query)
    ranked: list[tuple[float, dict]] = []
    for doc in _indexed():
        if kind and doc["kind"] != kind:
            continue
        if not _applicable(doc, as_of):
            continue
        overlap = q_tokens & doc["_tokens"]
        tag_hit = sum(1 for t in doc["tags"] if t.lower() in query or t in overlap)
        if not overlap and not tag_hit:
            continue
        score = len(overlap) + tag_hit * 2
        if doc["title"] in query or any(t in query for t in doc["tags"] if len(t) >= 2):
            score += 3
        ranked.append((score, doc))
    ranked.sort(key=lambda x: (-x[0], x[1]["id"]))
    hits = []
    for score, doc in ranked[:top_k]:
        meta = _meta_of(doc)
        hits.append(
            {
                "id": doc["id"],
                "kind": doc["kind"],
                "kind_label": _KIND_LABEL.get(doc["kind"], doc["kind"]),
                "title": doc["title"],
                "source": doc["source"],
                "snippet": doc["body"],
                "score": score,
                "article": _article_of(doc),
                "effective_date": meta["effective_date"],
                "expiry_date": meta["expiry_date"],
                "version": meta["version"],
                "as_of": as_of,
                "data_note": "synthetic-paraphrase",
            }
        )
    return hits


def retrieve_for_alert(alert_type: str, industry: str, as_of: str = "") -> list[dict]:
    """按告警类型和行业各检索一截，再补监管要素，去重后给 Agent 引用。"""
    seen: set[str] = set()
    merged: list[dict] = []
    queries = [
        (f"{alert_type} {industry} 调查要点", None),
        (alert_type, "typology"),
        (industry, "industry"),
        ("可疑交易报告要素 排除理由 人工签发 补正", "regulation"),
        ("质疑复核 确认偏误", "process"),
    ]
    for q, kind in queries:
        for hit in search_knowledge(q, kind=kind, top_k=2, as_of=as_of):
            if hit["id"] in seen or hit["score"] < 3:
                continue
            seen.add(hit["id"])
            merged.append(hit)
    return merged[:8]
