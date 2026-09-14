from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from .knowledge_statutes import STATUTES

# 作业口径摘录：供调查工作台引用，不是替代现行法律全文。
PLAYBOOK: list[dict] = [
    {
        "id": "KB-REG-01",
        "kind": "regulation",
        "title": "可疑交易须人工分析并记录过程",
        "source": "《反洗钱法》第三十五条、第五十三条；大额交易和可疑交易报告作业要求（转述）",
        "tags": ["人工分析", "过程记录", "可疑交易", "调查", "报告"],
        "body": "金融机构发现或者有合理理由怀疑客户、客户的资金或者其他资产与洗钱、恐怖融资等犯罪活动有关的，应当提交可疑交易报告。报告前须开展人工识别与分析，完整记录分析过程、依据的交易、客户尽职调查情况和结论，不得仅以系统自动预警或模型输出代替人工判断。对应《反洗钱法》第三十五条及大额交易和可疑交易报告管理办法。",
    },
    {
        "id": "KB-REG-02",
        "kind": "regulation",
        "title": "排除告警须记录合理理由",
        "source": "《反洗钱法》第三十五条；大额交易和可疑交易报告管理办法第十四条（2025年修订，转述）",
        "tags": ["排除", "理由", "误报", "关闭", "批发", "经营", "人工分析"],
        "body": "监测系统命中后，若经人工分析、识别认为不构成可疑，仍须记录分析排除的合理理由，例如交易与客户身份、职业或经营特征相符。不能只点关闭、不留痕迹。对应《大额交易和可疑交易报告管理办法》第十四条。",
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
        "source": "《反洗钱法》第三十五条；人民银行关于可疑交易报告补正时限的执行要求（转述）",
        "tags": ["补正", "五日", "要素", "质量"],
        "body": "监测中心认为要素不全或填写错误的，可退回补正。机构一般应在五个工作日内补正。调查工作台的价值是先把要素和证据编号写全，降低补正。",
    },
    {
        "id": "KB-REG-05",
        "kind": "regulation",
        "title": "上报前须审定，不得系统自动直报",
        "source": "《反洗钱法》第八条、第三十五条；管理办法关于审定报送的要求（转述）",
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

DOCUMENTS: list[dict] = [*PLAYBOOK, *STATUTES]

_KIND_LABEL = {
    "regulation": "监管要素",
    "typology": "调查类型学",
    "industry": "行业基线",
    "process": "作业规程",
}

_DOC_META = {
    "effective_date": "2017-01-01",
    "expiry_date": None,
    "version": "playbook-v2",
    "source_note": "作业口径转述 + 现行法律规章官方文本",
}

_CN_NUM = "零〇一二三四五六七八九十百千0-9"
_ART_HEAD = re.compile(rf"(?m)^(第[{_CN_NUM}]+条)\s*")
_ART_LABEL = re.compile(rf"第([{_CN_NUM}]+)条")

# 调查场景常用同义扩展，仅用于检索扩写，不改正文。
_QUERY_EXPAND: dict[str, list[str]] = {
    "排除": ["排除理由", "不作为可疑", "关闭"],
    "误报": ["排除", "经营解释"],
    "人工": ["人工分析", "人工识别"],
    "尽调": ["尽职调查", "了解你的客户"],
    "受益人": ["受益所有人"],
    "UBO": ["受益所有人"],
    "STR": ["可疑交易报告"],
    "CTR": ["大额交易"],
}


def _cn_to_int(s: str) -> int:
    s = (s or "").replace("〇", "零")
    digits = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    total = 0
    if "百" in s:
        i = s.index("百")
        total += digits.get(s[:i] or "一", 1) * 100
        s = s[i + 1 :]
    if s.startswith("十"):
        return total + 10 + digits.get(s[1:], 0)
    if "十" in s:
        i = s.index("十")
        return total + digits.get(s[:i] or "一", 1) * 10 + digits.get(s[i + 1 :], 0)
    return total + digits.get(s, 0)


def _article_of(doc: dict) -> str:
    if doc.get("article"):
        return str(doc["article"])
    blob = f"{doc.get('source') or ''} {doc.get('title') or ''}"
    found = re.findall(rf"第[{_CN_NUM}]+条", blob)
    if not found:
        return ""
    if len(found) == 1:
        return found[0]
    return f"{found[0]}至{found[-1]}"


def _applicable(doc: dict, as_of: str) -> bool:
    if not as_of:
        return True
    start = doc.get("effective_date") or _DOC_META["effective_date"]
    end = doc.get("expiry_date")
    if start and as_of < start:
        return False
    if end and as_of > end:
        return False
    return True


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    parts = [p for p in re.split(r"[\s,，。；、/（）()「」【】：:#\-]+", text) if len(p) >= 2]
    hans = re.findall(r"[\u4e00-\u9fff]+", text)
    extra: list[str] = []
    for h in hans:
        extra.append(h)
        if len(h) >= 4:
            extra.extend(h[i : i + 2] for i in range(len(h) - 1))
    ascii_words = re.findall(r"[a-z0-9]{3,}", text)
    return {t for t in [*parts, *extra, *ascii_words] if t}


def _expand_query(query: str) -> str:
    extra: list[str] = []
    for key, vals in _QUERY_EXPAND.items():
        if key.lower() in query.lower() or key in query:
            extra.extend(vals)
    return f"{query} {' '.join(extra)}".strip()


def _char_ngrams(text: str, n: int = 2) -> list[str]:
    cleaned = re.sub(r"\s+", "", (text or "").lower())
    if len(cleaned) < n:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def _tfidf_vec(tf: Counter[str], df: Counter[str], n_docs: int) -> dict[str, float]:
    if not tf or n_docs <= 0:
        return {}
    total = float(sum(tf.values())) or 1.0
    out: dict[str, float] = {}
    for term, cnt in tf.items():
        idf = math.log((1 + n_docs) / (1 + df.get(term, 0))) + 1.0
        out[term] = (cnt / total) * idf
    return out


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    if dot <= 0:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _snippet(text: str, limit: int = 360) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def _split_articles(body: str) -> list[tuple[str, int, str]]:
    """返回 (条款标签, 条款号, 正文含标签)。"""
    text = (body or "").strip()
    if not text:
        return []
    parts = _ART_HEAD.split(text)
    if len(parts) < 3:
        return []
    out: list[tuple[str, int, str]] = []
    i = 1
    while i < len(parts) - 1:
        head, chunk = parts[i], parts[i + 1]
        m = _ART_LABEL.fullmatch(head)
        if not m:
            i += 2
            continue
        n = _cn_to_int(m.group(1))
        content = chunk.strip()
        if n and content:
            out.append((head, n, f"{head}\n{content}"))
        i += 2
    return out


def _chunk_document(doc: dict) -> list[dict]:
    """官方规章按条切块；作业摘录保持整篇。"""
    if doc.get("data_note") != "official-statute":
        return [{**doc, "parent_id": doc["id"], "chunk_kind": "doc"}]
    articles = _split_articles(doc.get("body") or "")
    if not articles:
        return [{**doc, "parent_id": doc["id"], "chunk_kind": "doc"}]
    chunks: list[dict] = []
    for label, num, body in articles:
        chunks.append(
            {
                **doc,
                "id": f"{doc['id']}-a{num}",
                "parent_id": doc["id"],
                "chunk_kind": "article",
                "article": label,
                "article_no": num,
                "title": f"{doc['title']} · {label}",
                "body": body,
                "source": f"{doc.get('source') or ''}{label}",
            }
        )
    return chunks


@lru_cache(maxsize=1)
def _search_units() -> list[dict]:
    units: list[dict] = []
    for doc in DOCUMENTS:
        units.extend(_chunk_document(doc))
    return units


@lru_cache(maxsize=1)
def _hybrid_index() -> dict:
    units = _search_units()
    n_docs = len(units)
    df: Counter[str] = Counter()
    prepared: list[dict] = []
    for unit in units:
        blob = " ".join(
            [
                unit["id"],
                unit.get("parent_id") or "",
                unit["title"],
                unit["body"],
                " ".join(unit.get("tags") or []),
                unit.get("article") or "",
            ]
        )
        grams = _char_ngrams(blob, 2)
        tf = Counter(grams)
        df.update(tf.keys())
        prepared.append(
            {
                **unit,
                "_tokens": _tokens(blob),
                "_tf": tf,
            }
        )
    for row in prepared:
        row["_vec"] = _tfidf_vec(row.pop("_tf"), df, n_docs)
        row["_norm"] = math.sqrt(sum(v * v for v in row["_vec"].values())) or 1.0
    return {"units": prepared, "df": df, "n_docs": n_docs}


def corpus_size() -> int:
    """目录条目数（章/篇），供健康检查展示。"""
    return len(DOCUMENTS)


def search_unit_count() -> int:
    return len(_search_units())


def retrieval_mode() -> str:
    return "hybrid-keyword-tfidf"


def _doc_view(d: dict, *, as_of: str = "") -> dict:
    return {
        "id": d["id"],
        "parent_id": d.get("parent_id") or d["id"],
        "chunk_kind": d.get("chunk_kind") or "doc",
        "kind": d["kind"],
        "kind_label": _KIND_LABEL.get(d["kind"], d["kind"]),
        "title": d["title"],
        "source": d["source"],
        "tags": d["tags"],
        "body": d["body"],
        "article": _article_of(d),
        "article_no": d.get("article_no"),
        "effective_date": d.get("effective_date") or _DOC_META["effective_date"],
        "expiry_date": d.get("expiry_date") if "expiry_date" in d else _DOC_META["expiry_date"],
        "version": d.get("version") or _DOC_META["version"],
        "data_note": d.get("data_note") or "synthetic-paraphrase",
        "as_of": as_of,
    }


def list_knowledge() -> list[dict]:
    return [_doc_view(d) for d in DOCUMENTS]


def get_knowledge(doc_id: str) -> dict | None:
    key = str(doc_id or "").strip()
    if not key:
        return None
    for d in DOCUMENTS:
        if d["id"] == key:
            return _doc_view(d)
    for u in _search_units():
        if u["id"] == key:
            return _doc_view(u)
    return None


def search_knowledge(query: str, *, kind: str | None = None, top_k: int = 4, as_of: str = "") -> list[dict]:
    """关键词重叠 + 字符二元组 TF-IDF 余弦的混合检索；规章按条切块。"""
    expanded = _expand_query(query)
    q_tokens = _tokens(expanded)
    q_tf = Counter(_char_ngrams(expanded, 2))
    index = _hybrid_index()
    q_vec = _tfidf_vec(q_tf, index["df"], index["n_docs"])

    ranked: list[tuple[float, float, float, dict]] = []
    for doc in index["units"]:
        if kind and doc["kind"] != kind:
            continue
        if not _applicable(doc, as_of):
            continue
        overlap = q_tokens & doc["_tokens"]
        tag_hit = sum(1 for t in doc["tags"] if t.lower() in query or t in overlap or t in expanded)
        kw = float(len(overlap) + tag_hit * 2)
        if doc["title"] in query or any(t in query for t in doc["tags"] if len(t) >= 2):
            kw += 3
        # 查询里直接点名条款号时抬升对应切块
        art = doc.get("article") or ""
        if art and art in query:
            kw += 6
        if doc.get("article_no") and re.search(rf"(?:第)?{doc['article_no']}条", query):
            kw += 4
        vec = _cosine(q_vec, doc["_vec"])
        if kw <= 0 and vec < 0.08:
            continue
        # 融合：关键词主导精确命中，向量补语义邻近
        score = kw + 12.0 * vec
        ranked.append((score, kw, vec, doc))

    ranked.sort(key=lambda x: (-x[0], x[3]["id"]))
    hits = []
    for score, kw, vec, doc in ranked[:top_k]:
        hits.append(
            {
                **_doc_view(doc, as_of=as_of),
                "snippet": _snippet(doc["body"]),
                "score": round(score, 4),
                "score_keyword": round(kw, 4),
                "score_vector": round(vec, 4),
                "retrieval": retrieval_mode(),
            }
        )
    return hits


def retrieve_for_alert(alert_type: str, industry: str, as_of: str = "") -> list[dict]:
    """按告警类型和行业检索，并优先覆盖 STR 人工分析 / 反洗钱法核心义务条款。"""
    seen_ids: set[str] = set()
    seen_parents: set[str] = set()
    merged: list[dict] = []

    def _take(hits: list[dict], *, min_score: float = 2.5) -> None:
        for hit in hits:
            if hit["id"] in seen_ids or hit["score"] < min_score:
                continue
            parent = hit.get("parent_id") or hit["id"]
            # 同一规章篇目只保留一条最高分切块，给类型学/作业摘录留位
            if hit.get("chunk_kind") == "article" and parent in seen_parents:
                continue
            seen_ids.add(hit["id"])
            seen_parents.add(parent)
            merged.append(hit)

    queries = [
        (f"{alert_type} {industry} 调查要点", None, 2),
        (alert_type, "typology", 2),
        (industry, "industry", 2),
        ("可疑交易 人工分析 排除理由 第十四条", "regulation", 3),
        ("反洗钱法 第三十五条 可疑交易报告", "regulation", 2),
        ("尽职调查 受益所有人 保存十年", "regulation", 2),
        ("可疑交易报告要素 补正 人工签发", "regulation", 2),
        ("质疑复核 确认偏误", "process", 1),
    ]
    for q, kind, k in queries:
        _take(search_knowledge(q, kind=kind, top_k=k, as_of=as_of))
        if len(merged) >= 10:
            break
    return merged[:10]
