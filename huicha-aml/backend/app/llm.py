from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy.orm import Session

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


def llm_configured() -> bool:
    try:
        require_api_key()
        return True
    except RuntimeError:
        return False


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


def normalize_challenger_items(items: list, *, privacy: PrivacyMap | None = None) -> list[dict]:
    """脱敏还原 Challenger JSON，不做编号校验。"""
    rows: list[dict] = []
    for it in items[:3]:
        if not isinstance(it, dict):
            continue
        claim = str(it.get("claim") or it.get("title") or "").strip()
        detail = str(it.get("detail") or "").strip()
        if privacy:
            claim = privacy.unmask_text(claim)
            detail = privacy.unmask_text(detail)
        raw_ids = it.get("evidence_ids") or []
        if isinstance(raw_ids, str):
            raw_ids = [raw_ids]
        evidence_ids = []
        for eid in raw_ids:
            eid = str(eid).strip()
            if privacy:
                eid = privacy.unmask_text(eid)
            if eid:
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
                "delta": round(delta, 4),
            }
        )
    return rows


def validate_challenger_items(
    items: list,
    *,
    allowed_evidence: set[str],
    privacy: PrivacyMap | None = None,
) -> tuple[list[dict], float]:
    """脱敏还原后交给 validator，不再另写一套 delta/证据规则。"""
    rows = normalize_challenger_items(items, privacy=privacy)
    kept, total, _rejected = filter_challenger_items(rows, allowed=set(allowed_evidence))
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
) -> tuple[list[dict], dict]:
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
        "allowed_evidence_ids": allowed_evidence[:40],
        "delta_bound": DELTA_BOUND,
    }
    if privacy:
        context = privacy.mask_obj(context)

    key = _cache_key("challenger_v2", context)
    cached = _cache_get(db, key)
    if cached:
        text, usage = cached
    else:
        from .prompts import PROMPTS

        system = PROMPTS["challenger_v2"]
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
                    {"role": "system", "content": '只输出 {"items":[{"claim":"...","detail":"...","evidence_ids":[],"delta":0}]}'},
                    {"role": "user", "content": text[:2000]},
                ],
                temperature=0.0,
                max_tokens=500,
            )
        _cache_put(db, key, "challenger_v2", text, usage)

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
