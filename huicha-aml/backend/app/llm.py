from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

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


def chat(messages: list[dict], *, temperature: float = 0.2, max_tokens: int = 900) -> str:
    """Call Bailian / DashScope OpenAI-compatible Chat Completions. No mock fallback."""
    api_key = require_api_key()
    base = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = llm_model()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"百炼调用失败 model={model} HTTP {e.code}: {detail[:400]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"百炼网络错误 model={model}: {e}") from e
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise RuntimeError(f"百炼返回无法解析 model={model}: {data!r}"[:500]) from e


def enrich_challenger(
    *,
    alert: dict,
    customer: dict,
    findings: list[dict],
    baseline: dict,
    kb_hits: list[dict],
    score_hints: list[dict],
) -> list[dict]:
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
        "findings": [{"title": f["title"], "detail": f["detail"]} for f in findings],
        "kb": [{"id": h["id"], "title": h["title"], "snippet": h["snippet"]} for h in kb_hits[:5]],
        "score_hints": score_hints,
    }
    system = (
        "你是银行反洗钱调查中的质疑角色 Challenger。"
        "任务是寻找可解释的经营/用途反证，抑制确认偏误。"
        "只能使用给定 JSON 中的事实，禁止编造账号、金额、交易编号、客户名。"
        "可参考 score_hints，但文案必须自己组织，不要照抄成模板腔。"
        "输出严格 JSON 数组，每项含 title、detail 两个字符串字段，最多 3 条。"
        "若反证不足，也要明确写清「未找到强开脱理由」。"
    )
    text = chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        temperature=0.25,
        max_tokens=700,
    )
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        items = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Challenger 返回非 JSON：{text[:300]}") from e
    out = []
    for it in items[:3]:
        title = str(it.get("title", "")).strip()
        detail = str(it.get("detail", "")).strip()
        if title and detail:
            out.append({"title": title, "detail": detail})
    if not out:
        raise RuntimeError("Challenger 未返回有效条目")
    return out


def enrich_report_reason(
    *,
    alert: dict,
    customer: dict,
    conclusion_label: str,
    findings: list[dict],
    challenger: list[dict],
    kb_hits: list[dict],
    sample_ids: str,
    draft_reason: str,
) -> str:
    context = {
        "conclusion": conclusion_label,
        "alert_type": alert["alert_type"],
        "account_id": alert["account_id"],
        "customer_name": customer["name"],
        "customer_id": customer["id"],
        "industry": customer["industry"],
        "findings": [f["title"] for f in findings],
        "challenger": [c.get("title", "") for c in challenger],
        "kb_ids": [h["id"] for h in kb_hits if h["kind"] == "regulation"][:3],
        "allowed_tx_ids": sample_ids,
        "draft_reason": draft_reason,
    }
    system = (
        "你是反洗钱 Reporter，只润色「结论与理由」段落。"
        "必须保持与给定结论一致；只能引用 allowed_tx_ids 中的交易编号和已给出的客户号/账号。"
        "禁止新增任何未出现的账号、金额数字、交易编号。"
        "不要写自动报送；强调须人工签发。"
        "直接输出一段中文，不要 Markdown，不要标题。"
    )
    text = chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        temperature=0.2,
        max_tokens=500,
    )
    text = text.strip().strip("`")
    if not text:
        raise RuntimeError("Reporter 返回空文本")
    return text
