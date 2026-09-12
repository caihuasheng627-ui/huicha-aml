from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy.orm import Session

from .predicates import catalog_for_prompt, case_facts, stub_challenger_item
from .privacy import PrivacyMap
from .validator import DELTA_BOUND, filter_challenger_items

_ENV_LOADED = False
DEFAULT_MODEL = "deepseek-v4-flash-0731"


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def require_api_key() -> str:
    _load_env()
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，请在 backend/.env 填写百炼密钥")
    return api_key


def llm_model() -> str:
    _load_env()
    return os.getenv("DASHSCOPE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def llm_stub_enabled() -> bool:
    _load_env()
    return os.getenv("HUICHA_LLM_STUB", "").strip().lower() in {"1", "true", "yes", "on"}


def llm_configured() -> bool:
    if llm_stub_enabled():
        return True
    try:
        require_api_key()
        return True
    except RuntimeError:
        return False


def llm_mode() -> str:
    if llm_stub_enabled():
        return "stub"
    try:
        require_api_key()
        return "bailian"
    except RuntimeError:
        return "off"


def _offline_stub_chat(messages: list[dict]) -> tuple[str, dict]:
    usage = {
        "prompt_tokens": 8,
        "completion_tokens": 16,
        "total_tokens": 24,
        "cached": False,
        "model": "stub",
    }
    sys = messages[0]["content"] if messages else ""
    user = messages[-1]["content"] if messages else ""
    if "调查 Judge" in sys or "disposition" in sys:
        try:
            data = json.loads(user)
        except json.JSONDecodeError:
            data = {}
        findings = data.get("findings") or []
        codes = {str(f.get("code") or "") for f in findings}
        if {"structuring", "funnel", "layering", "watchlist"} & codes:
            disposition, confidence = "suggest_report", 0.78
        elif {"unregistered-counterparty"} & codes or data.get("missing_evidence"):
            disposition, confidence = "observe", 0.62
        else:
            disposition, confidence = "exclude", 0.72
        support = [
            eid
            for f in findings
            if f.get("polarity") == "support"
            for eid in (f.get("evidence_ids") or [])
        ][:6]
        counter = [
            eid
            for f in findings
            if f.get("polarity") == "counter"
            for eid in (f.get("evidence_ids") or [])
        ][:6]
        cited = support or counter or list(data.get("allowed_evidence_ids") or [])[:2]
        return (
            json.dumps(
                {
                    "disposition": disposition,
                    "confidence": confidence,
                    "typologies": sorted(codes & {"structuring", "funnel", "layering", "watchlist"}),
                    "supporting_evidence_ids": support,
                    "contradicting_evidence_ids": counter,
                    "missing_evidence": data.get("missing_evidence") or [],
                    "rationale": [{"text": "依据本案已调取事实形成初步建议。", "evidence_ids": cited}],
                    "next_actions": ["由调查员复核证据与缺失材料"],
                },
                ensure_ascii=False,
            ),
            usage,
        )
    if "完整四段调查底稿" in sys:
        try:
            data = json.loads(user)
        except json.JSONDecodeError:
            data = {}
        ids = "、".join((data.get("evidence_ids") or [])[:6]) or "（无）"
        conclusion = data.get("conclusion_label") or "待审"
        return (
            "\n".join(
                [
                    f"【资金交易及客户行为】已调取本案客户与交易事实，关键证据 {ids}。",
                    f"【疑点分析】依据已核验指标形成{conclusion}的初步建议，证据 {ids}。",
                    f"【反证与缺失证据】已区分反向证据和待补材料，证据 {ids}。",
                    f"【结论与理由】{conclusion}。须人工签发，不可自动报送，证据 {ids}。",
                ]
            ),
            usage,
        )
    if "Challenger" in sys or "质疑" in sys or "delta" in sys or "predicate" in sys:
        try:
            data = json.loads(user)
        except json.JSONDecodeError:
            data = {}
        item = stub_challenger_item(
            data if isinstance(data, dict) else {},
            claim="测试反证",
            detail="仅用于本地 stub，不含虚构账号。",
            delta=-0.12,
        )
        return json.dumps({"items": [item]}, ensure_ascii=False), usage
    try:
        data = json.loads(user)
    except json.JSONDecodeError:
        data = {}
    text = (
        f"结论为{data.get('conclusion') or '待审'}。"
        f"客户{data.get('customer_name') or ''}（{data.get('customer_id') or ''}，账户{data.get('account_id') or ''}）"
        f"相关交易编号：{data.get('allowed_tx_ids') or ''}。须人工签发，不可自动报送。"
    )
    return text, usage


def _cache_key(kind: str, payload: dict) -> str:
    raw = json.dumps({"kind": kind, "model": llm_model(), "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(db: Session | None, key: str) -> tuple[str, dict] | None:
    if db is None:
        return None
    from .models import LlmCache

    row = db.get(LlmCache, key)
    if not row:
        return None
    try:
        usage = json.loads(row.usage_json or "{}")
    except json.JSONDecodeError:
        usage = {}
    return row.response_text, {**usage, "cached": True}


def _cache_put(db: Session | None, key: str, kind: str, text: str, usage: dict) -> None:
    if db is None:
        return
    from .models import LlmCache

    row = db.get(LlmCache, key)
    blob = json.dumps(usage or {}, ensure_ascii=False)
    if row:
        row.response_text = text
        row.usage_json = blob
        row.model = llm_model()
        row.kind = kind
    else:
        db.add(
            LlmCache(
                cache_key=key,
                kind=kind,
                model=llm_model(),
                response_text=text,
                usage_json=blob,
            )
        )
    try:
        db.commit()
    except Exception:
        db.rollback()


def chat(messages: list[dict], *, temperature: float = 0.0, max_tokens: int = 900) -> tuple[str, dict]:
    if llm_stub_enabled():
        return _offline_stub_chat(messages)
    api_key = require_api_key()
    base = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = llm_model()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "enable_thinking": False,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"百炼调用失败 model={model} HTTP {e.code}: {detail[:400]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"百炼网络错误 model={model}: {e}") from e
    try:
        msg = data["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        if not content:
            content = (msg.get("reasoning_content") or "").strip()
        if not content:
            raise RuntimeError(f"百炼返回空 content model={model}")
        usage = data.get("usage") or {}
        return content, {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "finish_reason": data["choices"][0].get("finish_reason"),
            "cached": False,
            "model": model,
        }
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise RuntimeError(f"百炼返回无法解析 model={model}: {data!r}"[:500]) from e


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip().strip("`").strip()


def _extract_json_array(text: str) -> list:
    raw = _strip_fence(text)
    if not raw:
        raise RuntimeError("Challenger 返回空文本")
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I).strip()
    candidates: list[str] = []
    obj_match = re.search(r"\{[\s\S]*\"items\"[\s\S]*\}", raw)
    if obj_match:
        candidates.append(obj_match.group(0))
    candidates.append(raw)
    start, end = raw.find("["), raw.rfind("]")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    last_err: Exception | None = None
    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and ("title" in data or "claim" in data):
                return [data]
        except json.JSONDecodeError as e:
            last_err = e
            continue
    raise RuntimeError(f"Challenger 返回非 JSON：{text[:400]}") from last_err


def _extract_json_object(text: str) -> dict:
    raw = _strip_fence(text)
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I).strip()
    candidates = [raw]
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"模型返回非 JSON 对象：{text[:400]}")


JUDGE_MAX_TOKENS = 2400
REPORTER_MAX_TOKENS = 1800


def _parse_model_json(text: str, usage: dict, *, role: str) -> dict:
    """截断（finish_reason=length）与非 JSON 分开报错，便于修复轮次给出针对性提示。"""
    try:
        return _extract_json_object(text)
    except RuntimeError as exc:
        if (usage or {}).get("finish_reason") == "length":
            raise RuntimeError(
                f"{role} 输出超过 max_tokens 被截断（completion_tokens={usage.get('completion_tokens')}），"
                "请压缩证据引用数量"
            ) from exc
        raise


def _unmask_value(value, privacy: PrivacyMap | None):
    if privacy is None:
        return value
    if isinstance(value, str):
        return privacy.unmask_text(value)
    if isinstance(value, list):
        return [_unmask_value(v, privacy) for v in value]
    if isinstance(value, dict):
        return {k: _unmask_value(v, privacy) for k, v in value.items()}
    return value


def normalize_challenger_items(items: list, *, privacy: PrivacyMap | None = None) -> list[dict]:
    """脱敏还原 Challenger JSON，不做编号校验。"""
    rows: list[dict] = []
    for it in items[:3]:
        if not isinstance(it, dict):
            continue
        claim = str(it.get("claim") or it.get("title") or "").strip()
        detail = str(it.get("detail") or "").strip()
        predicate = str(it.get("predicate") or "").strip()
        args = it.get("args") if isinstance(it.get("args"), dict) else {}
        if privacy:
            claim = privacy.unmask_text(claim)
            detail = privacy.unmask_text(detail)
            args = _unmask_value(args, privacy)
        raw_ids = it.get("evidence_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        evidence_ids = []
        for eid in raw_ids:
            eid = str(eid).strip()
            if privacy:
                eid = privacy.unmask_text(eid)
            if eid and eid not in evidence_ids:
                evidence_ids.append(eid)
        for eid in args.get("tx_ids") or [] if isinstance(args, dict) else []:
            eid = str(eid).strip()
            if eid and eid not in evidence_ids:
                evidence_ids.append(eid)
        try:
            delta = float(it.get("delta", 0))
        except (TypeError, ValueError):
            delta = 0.0
        rows.append(
            {
                "title": claim,
                "claim": claim,
                "detail": detail or claim,
                "evidence_ids": evidence_ids,
                "predicate": predicate,
                "args": args,
                "delta": round(delta, 4),
            }
        )
    return rows


def validate_challenger_items(
    items: list,
    *,
    allowed_evidence: set[str],
    privacy: PrivacyMap | None = None,
    facts: dict | None = None,
) -> tuple[list[dict], float]:
    """脱敏还原后交给 validator，不再另写一套 delta/证据规则。"""
    rows = normalize_challenger_items(items, privacy=privacy)
    kept, total, _rejected = filter_challenger_items(rows, allowed=set(allowed_evidence), facts=facts)
    return kept, total


def enrich_challenger(
    *,
    db: Session | None = None,
    privacy: PrivacyMap | None = None,
    alert: dict,
    customer: dict,
    findings: list[dict],
    baseline: dict,
    kb_hits: list[dict],
    score_hints: list[dict],
    allowed_evidence: list[str],
    transactions: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    facts = case_facts(transactions=transactions, customer=customer, account_id=alert.get("account_id") or "")
    context = {
        "alert_type": alert["alert_type"],
        "customer": {
            "name": customer["name"],
            "id": customer["id"],
            "kind": customer["kind"],
            "industry": customer["industry"],
            "opened_at": customer["opened_at"],
            "kyc_level": customer["kyc_level"],
            "summary": customer["summary"],
        },
        "baseline_note": baseline.get("peer_note"),
        "findings": [{"title": f["title"], "detail": f["detail"], "evidence_ids": f.get("evidence_ids", [])} for f in findings],
        "kb": [{"id": h["id"], "title": h["title"], "snippet": h["snippet"]} for h in kb_hits[:5]],
        "score_hints": score_hints,
        "allowed_evidence_ids": list(dict.fromkeys([*(t["id"] for t in facts["transactions"] if t.get("id")), *allowed_evidence]))[:80],
        "delta_bound": DELTA_BOUND,
        "transactions": facts["transactions"][:24],
        "allowed_predicates": catalog_for_prompt(),
    }
    if privacy:
        context = privacy.mask_obj(context)

    key = _cache_key("challenger_v3", context)
    cached = _cache_get(db, key)
    if cached:
        text, usage = cached
    else:
        from .prompts import PROMPTS

        system = PROMPTS["challenger_v3"]
        text, usage = chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=700,
        )
        try:
            _extract_json_array(text)
        except RuntimeError:
            text, usage = chat(
                [
                    {
                        "role": "system",
                        "content": (
                            '只输出 {"items":[{"claim":"...","detail":"...","evidence_ids":[],'
                            '"predicate":"...","args":{"tx_ids":[]},"delta":0}]}'
                        ),
                    },
                    {"role": "user", "content": text[:2000]},
                ],
                temperature=0.0,
                max_tokens=500,
            )
        _cache_put(db, key, "challenger_v3", text, usage)

    items = _extract_json_array(text)
    rows = normalize_challenger_items(items, privacy=privacy)
    if not rows:
        raise RuntimeError(f"Challenger 未返回有效条目：{text[:300]}")
    return rows, usage


def enrich_report_reason(
    *,
    db: Session | None = None,
    privacy: PrivacyMap | None = None,
    alert: dict,
    customer: dict,
    conclusion_label: str,
    findings: list[dict],
    challenger: list[dict],
    kb_hits: list[dict],
    sample_ids: str,
    draft_reason: str,
    prior_issues: list[dict] | None = None,
) -> tuple[str, dict]:
    context = {
        "conclusion": conclusion_label,
        "alert_type": alert["alert_type"],
        "account_id": alert["account_id"],
        "customer_name": customer["name"],
        "customer_id": customer["id"],
        "industry": customer["industry"],
        "findings": [f["title"] for f in findings],
        "challenger": [c.get("claim") or c.get("title", "") for c in challenger],
        "kb_ids": [h["id"] for h in kb_hits if h["kind"] == "regulation"][:3],
        "allowed_tx_ids": sample_ids,
        "draft_reason": draft_reason,
        "avoid_tokens": [i.get("token") for i in (prior_issues or []) if i.get("token")],
    }
    if privacy:
        context = privacy.mask_obj(context)

    key = None if prior_issues else _cache_key("reporter_v2", context)
    if key:
        cached = _cache_get(db, key)
        if cached:
            text, usage = cached
            text = privacy.unmask_text(_strip_fence(text)) if privacy else _strip_fence(text)
            return text, usage

    system = (
        "你是反洗钱 Reporter，只润色「结论与理由」。"
        "保持结论一致；只能引用 allowed_tx_ids 与已给客户号/账号占位符。"
        "禁止新增未出现的账号、金额、交易编号。若有 avoid_tokens 不得再出现。"
        "强调须人工签发。直接输出中文一段，不要 Markdown/代码块。"
    )
    text, usage = chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=500,
    )
    text = _strip_fence(text)
    if privacy:
        text = privacy.unmask_text(text)
    if not text:
        raise RuntimeError("Reporter 返回空文本")
    if key:
        _cache_put(db, key, "reporter_v2", text if not privacy else privacy.mask_text(text), usage)
    return text, usage


def enrich_judge(
    *,
    db: Session | None = None,
    privacy: PrivacyMap | None = None,
    alert: dict,
    customer: dict,
    findings: list[dict],
    transactions: list[dict],
    baseline: dict,
    kb_hits: list[dict],
    allowed_evidence: list[str],
    missing_evidence: list[str] | None = None,
    prior_issues: list[dict] | None = None,
) -> tuple[dict, dict]:
    context = {
        "alert_trigger": {
            "type": alert.get("alert_type"),
            "source": alert.get("upstream"),
            "note": "仅为待复核线索，不直接决定 disposition",
        },
        "customer": {
            key: customer.get(key)
            for key in ("id", "name", "kind", "industry", "opened_at", "kyc_level", "summary")
        },
        "findings": findings,
        "transactions": transactions[:30],
        "baseline": baseline,
        "knowledge": [
            {"id": h.get("id"), "kind": h.get("kind"), "title": h.get("title"), "snippet": h.get("snippet")}
            for h in kb_hits[:8]
        ],
        # 只把模型在上下文里能看到内容的编号列出来；EV- 内部编号没有对应描述，列出只会诱导误引。
        "allowed_evidence_ids": [e for e in allowed_evidence if not str(e).startswith("EV-")][:120],
        "missing_evidence": missing_evidence or [],
        "repair_issues": prior_issues or [],
        "output_limits": {
            "supporting_evidence_ids": 10,
            "contradicting_evidence_ids": 10,
            "rationale": 5,
            "evidence_ids_per_rationale": 6,
            "missing_evidence": 5,
            "next_actions": 5,
        },
    }
    if privacy:
        context = privacy.mask_obj(context)
    key = None if prior_issues else _cache_key("judge_v2", context)
    cached = _cache_get(db, key) if key else None
    if cached:
        text, usage = cached
        data = _extract_json_object(text)
    else:
        from .prompts import PROMPTS

        text, usage = chat(
            [
                {"role": "system", "content": PROMPTS["judge_v2"]},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=JUDGE_MAX_TOKENS,
        )
        data = _parse_model_json(text, usage, role="Judge")
        if key:
            _cache_put(db, key, "judge_v2", text, usage)
    return _unmask_value(data, privacy), usage


def enrich_full_report(
    *,
    db: Session | None = None,
    privacy: PrivacyMap | None = None,
    context: dict,
    prior_issues: list[dict] | None = None,
) -> tuple[str, dict]:
    payload = {**context, "repair_issues": prior_issues or []}
    if privacy:
        payload = privacy.mask_obj(payload)
    key = None if prior_issues else _cache_key("reporter_v3", payload)
    cached = _cache_get(db, key) if key else None
    if cached:
        text, usage = cached
    else:
        from .prompts import PROMPTS

        text, usage = chat(
            [
                {"role": "system", "content": PROMPTS["reporter_v3"]},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=REPORTER_MAX_TOKENS,
        )
        if usage.get("finish_reason") == "length":
            raise RuntimeError(
                f"Reporter 输出超过 max_tokens 被截断（completion_tokens={usage.get('completion_tokens')}）"
            )
        if key and _strip_fence(text):
            _cache_put(db, key, "reporter_v3", text, usage)
    text = _strip_fence(text)
    if privacy:
        text = privacy.unmask_text(text)
    if not text:
        raise RuntimeError("Reporter 返回空文本")
    return text, usage
