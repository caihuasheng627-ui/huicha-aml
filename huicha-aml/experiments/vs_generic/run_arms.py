"""跑 A0/A1/A2/A3/B。产品默认温度、出站检查和 prompt 版本都不改。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.decision import normalize_judge, verify_judge  # noqa: E402
from app.llm import (  # noqa: E402
    JUDGE_MAX_TOKENS,
    _extract_json_object,
    _load_env,
    _unmask_value,
    build_judge_context,
    chat,
    enrich_judge,
    llm_base_url,
    llm_model,
    llm_stub_enabled,
    require_api_key,
)
from app.metrics_lib import LABELS  # noqa: E402
from app.notes import facts_from_payload  # noqa: E402
from app.predicates import case_facts  # noqa: E402
from app.privacy import PrivacyLeakError, PrivacyMap  # noqa: E402
from app.prompts import PROMPTS, prompt_version  # noqa: E402
from app.tools import fact_check, hard_fact_issues  # noqa: E402
from experiments.vs_generic.build_attack_set import (  # noqa: E402
    ATTACK_PATH,
    STABILITY_PATH,
    SYN_ACCOUNT,
    SYN_ID,
    SYN_PHONE,
    load_struct_cases,
    write_inputs,
)
from experiments.vs_generic.render_generic import (  # noqa: E402
    A1_SYSTEM,
    generic_messages,
    render_case,
    render_leaks,
)
from experiments.vs_generic.score import case_valid_ids  # noqa: E402

import app.llm as llm_mod  # noqa: E402
import app.privacy as privacy_mod  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
BENCH = HERE.parent / "benchmark"
GAP_S = 0.15
PII_TOKENS = {"id": SYN_ID, "phone": SYN_PHONE, "account": SYN_ACCOUNT}

FULL_JOBS = (
    ("A0", "blind", None),
    ("A1", "blind", None),
    ("A2A3", "blind", None),
    ("A0", "blind_struct", None),
    ("A1", "blind_struct", None),
    ("A2A3", "blind_struct", None),
    ("A1", "attack", None),
    ("A3", "attack", None),
    ("A1", "stability", None),
    ("A3", "stability", None),
    ("B", "b", "deepseek-reasoner"),
)


class FatalAPIError(RuntimeError):
    pass


def sanitize(text: str) -> str:
    text = re.sub(r"Bearer\s+\S+", "Bearer ***", text or "")
    text = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-***", text)
    return text[:500]


def is_fatal(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if re.search(r"http\s+401\b", msg) or re.search(r"http\s+402\b", msg) or re.search(r"http\s+403\b", msg):
        return True
    needles = (
        "insufficient balance",
        "insufficient quota",
        "invalid api key",
        "authentication fails",
        "authentication error",
        "unauthorized",
        "余额不足",
        "欠费",
        "account overdue",
    )
    return any(item in msg for item in needles)


def is_retryable(exc: BaseException) -> bool:
    msg = str(exc)
    if re.search(r"HTTP\s+429\b", msg) or re.search(r"HTTP\s+5\d\d\b", msg):
        return True
    return "网络错误" in msg


def confirm_runtime() -> str:
    _load_env()
    os.environ.pop("HUICHA_LLM_STUB", None)
    base = llm_base_url()
    model = llm_model()
    if llm_stub_enabled():
        raise SystemExit("HUICHA_LLM_STUB 仍在生效，停止实验")
    if "api.deepseek.com" not in base:
        raise SystemExit(f"llm_base_url 不是 api.deepseek.com：{base}")
    if model != "deepseek-chat":
        raise SystemExit(f"默认模型不是 deepseek-chat：{model}")
    leaks = render_leaks(A1_SYSTEM)
    if leaks:
        raise SystemExit(f"A1 系统提示含禁止词：{leaks}")
    print(
        f"endpoint {base} default_model {model} key_present {bool(os.getenv('DEEPSEEK_API_KEY'))} stub {llm_stub_enabled()}",
        flush=True,
    )
    return model


def arm_blocked(arm: str, verify_hard: list, fact_hard: list) -> bool:
    if arm != "A3":
        return False
    return bool(verify_hard or fact_hard)


@contextmanager
def bypass_outbound_gate():
    """通用组不被产品出站闸门保护。chat() 用的是 llm 模块里的函数对象，两处都要换掉。"""
    old_privacy = privacy_mod.inspect_outbound
    old_llm = llm_mod.inspect_outbound

    def _noop(_messages) -> None:
        return None

    privacy_mod.inspect_outbound = _noop
    llm_mod.inspect_outbound = _noop
    try:
        yield
    finally:
        privacy_mod.inspect_outbound = old_privacy
        llm_mod.inspect_outbound = old_llm


class _Tap:
    def __init__(self) -> None:
        self.messages = None
        self.text = ""

    def __enter__(self) -> "_Tap":
        self._orig = llm_mod.chat

        def _wrapped(messages, **kwargs):
            self.messages = messages
            text, usage = self._orig(messages, **kwargs)
            self.text = text or ""
            return text, usage

        llm_mod.chat = _wrapped
        return self

    def __exit__(self, *exc) -> None:
        llm_mod.chat = self._orig


def call_with_retry(fn):
    delay = 1.5
    for attempt in range(6):
        try:
            return fn()
        except PrivacyLeakError:
            raise
        except FatalAPIError:
            raise
        except Exception as exc:
            if is_fatal(exc):
                raise FatalAPIError(sanitize(str(exc))) from None
            if is_retryable(exc) and attempt < 5:
                print(f"退避 {delay:.1f}s {sanitize(str(exc))[:180]}", flush=True)
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError("重试耗尽")


def _parse_vendor(data: dict, model: str) -> tuple[str, dict]:
    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    if not content:
        content = (msg.get("reasoning_content") or "").strip()
    if not content:
        raise RuntimeError(f"DeepSeek 返回空 content model={model}")
    usage = data.get("usage") or {}
    return content, {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "finish_reason": data["choices"][0].get("finish_reason"),
        "cached": False,
        "model": model,
    }


def post_omit_temperature(messages, *, model: str, max_tokens: int) -> tuple[str, dict, str]:
    """reasoner 拒绝 temperature 时的退路。仍先走当前的出站检查。"""
    llm_mod.inspect_outbound(messages)
    api_key = require_api_key()
    base = llm_base_url()
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek调用失败 model={model} HTTP {exc.code}: {detail[:400]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"DeepSeek网络错误 model={model}: {exc}") from exc
    text, usage = _parse_vendor(data, model)
    return text, usage, "direct_omit_temperature"


def invoke_chat(messages, *, temperature: float, model: str, max_tokens: int, reasoner: bool):
    def once(temp: float, mode: str):
        text, usage = chat(messages, temperature=temp, max_tokens=max_tokens, model=model)
        return text, usage, mode

    try:
        return call_with_retry(lambda: once(temperature, "chat"))
    except RuntimeError as exc:
        if not (reasoner and "temperature" in str(exc).lower()):
            raise
        print("reasoner 拒绝该 temperature，改试 1", flush=True)
    try:
        return call_with_retry(lambda: once(1.0, "chat_temperature_1"))
    except RuntimeError as exc:
        if "temperature" not in str(exc).lower():
            raise
        print("reasoner 仍拒绝 temperature，改为不传该字段", flush=True)
    return call_with_retry(lambda: post_omit_temperature(messages, model=model, max_tokens=max_tokens))


def judge_inputs(case: dict) -> dict:
    vig = case["vignette"]
    txs = list(vig.get("transactions") or [])
    findings = list(vig.get("findings") or [])
    customer = dict(vig.get("customer") or {})
    customer.setdefault("id", f"C-{case['case_id']}")
    alert = dict(vig.get("alert") or {})
    alert.setdefault("id", case["case_id"])
    alert.setdefault("alert_type", vig.get("alert_type") or "")
    alert.setdefault("upstream", "vs-generic")
    allowed = list(vig.get("allowed_evidence") or [])
    if not allowed:
        allowed = sorted(
            {t["id"] for t in txs if t.get("id")}
            | {e["id"] for e in vig.get("candidate_evidence") or []}
            | {eid for finding in findings for eid in finding.get("evidence_ids") or []}
        )
    return {
        "alert": alert,
        "customer": customer,
        "findings": findings,
        "transactions": txs,
        "baseline": dict(vig.get("baseline") or {}),
        "kb_hits": list(vig.get("kb_hits") or []),
        "allowed_evidence": allowed,
    }


def bundle_from(case: dict) -> dict:
    vig = case["vignette"]
    return {
        "customer": vig.get("customer") or {},
        "alert": vig.get("alert") or {},
        "transactions": vig.get("transactions") or [],
        "graph": vig.get("graph") or {},
        "watch_hits": vig.get("watch_hits") or [],
    }


def fact_payload(case: dict) -> dict:
    vig = case["vignette"]
    return facts_from_payload(
        {
            "alert": vig.get("alert") or {},
            "customer": vig.get("customer") or {},
            "transactions": vig.get("transactions") or [],
            "baseline": vig.get("baseline") or {},
            "graph": vig.get("graph") or {},
            "watch_hits": vig.get("watch_hits") or [],
            "kb_hits": vig.get("kb_hits") or [],
            "evidence": vig.get("candidate_evidence") or [],
            "findings": vig.get("findings") or [],
        }
    )


def pii_flags(blob: str) -> dict:
    blob = blob or ""
    return {key: token in blob for key, token in PII_TOKENS.items()}


def _clip(text: str, limit: int = 16000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


def _clip_messages(messages) -> list[dict]:
    clipped = []
    for msg in messages or []:
        content = str((msg or {}).get("content") or "")
        clipped.append(
            {
                "role": (msg or {}).get("role"),
                "content": content if len(content) <= 6000 else content[:6000] + "…[truncated]",
            }
        )
    return clipped


def _message_blob(messages) -> str:
    return "\n".join(str((msg or {}).get("content") or "") for msg in messages or [])


def load_split(name: str) -> list[dict]:
    filename = {"blind": "blind_set.json", "blind_struct": "struct_set.json", "struct": "struct_set.json"}[name]
    payload = json.loads((BENCH / filename).read_text(encoding="utf-8"))
    return list(payload["cases"])


def ensure_inputs() -> None:
    if not STABILITY_PATH.exists() or not ATTACK_PATH.exists():
        write_inputs()


def work_items(set_name: str, attack_kind: str | None, limit: int | None) -> list[tuple[dict, str]]:
    ensure_inputs()
    if set_name in {"blind", "blind_struct"}:
        rows = [(case, "") for case in load_split(set_name)]
    elif set_name in {"stability", "b"}:
        ids = json.loads(STABILITY_PATH.read_text(encoding="utf-8"))["case_ids"]
        by_id = {case["case_id"]: case for case in load_struct_cases()}
        missing = [cid for cid in ids if cid not in by_id]
        if missing:
            raise RuntimeError(f"稳定性名单缺案件 {missing[:3]}")
        rows = [(by_id[cid], "") for cid in ids]
    elif set_name == "attack":
        payload = json.loads(ATTACK_PATH.read_text(encoding="utf-8"))
        rows = []
        for item in payload["cases"]:
            if attack_kind and item["attack_kind"] != attack_kind:
                continue
            case = item["case"]
            case["_source_case_id"] = item["source_case_id"]
            rows.append((case, item["attack_kind"]))
    else:
        raise ValueError(set_name)
    if limit is not None:
        rows = rows[:limit]
    return rows


class Store:
    def __init__(self, no_write: bool, retry_errors: bool) -> None:
        self.no_write = no_write
        self.retry_errors = retry_errors
        self.dir = RUNS
        self._fh: dict[Path, object] = {}
        self._seen: dict[Path, set[tuple]] = {}
        if not no_write:
            self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, arm: str, set_name: str, model: str) -> Path:
        safe = model.replace("/", "_")
        return self.dir / f"{arm}_{set_name}_{safe}.jsonl"

    def seen(self, arm: str, set_name: str, model: str) -> set[tuple]:
        path = self.path(arm, set_name, model)
        if path not in self._seen:
            found: dict[tuple, dict] = {}
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("_meta"):
                        continue
                    key = (row.get("case_id"), int(row.get("repeat") or 0))
                    found[key] = row
            keys = set()
            for key, row in found.items():
                kind = row.get("error_kind") or ""
                if self.retry_errors and kind in {"api", "network"}:
                    continue
                keys.add(key)
            self._seen[path] = keys
        return self._seen[path]

    def has(self, arm: str, set_name: str, model: str, case_id: str, repeat: int) -> bool:
        if self.no_write:
            return False
        return (case_id, repeat) in self.seen(arm, set_name, model)

    def append(self, arm: str, set_name: str, model: str, row: dict) -> None:
        if self.no_write:
            return
        path = self.path(arm, set_name, model)
        if path not in self._fh:
            new_file = not path.exists() or path.stat().st_size == 0
            fh = path.open("a", encoding="utf-8")
            self._fh[path] = fh
            if new_file:
                meta = {
                    "_meta": True,
                    "arm": arm,
                    "set": set_name,
                    "model": model,
                    "prompt_judge": prompt_version("judge"),
                }
                fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        fh = self._fh[path]
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        self.seen(arm, set_name, model).add((row.get("case_id"), int(row.get("repeat") or 0)))

    def close(self) -> None:
        for fh in self._fh.values():
            fh.close()
        self._fh.clear()


def _base_row(**kwargs) -> dict:
    row = {
        "blocked": False,
        "parse_ok": False,
        "pred": None,
        "confidence": None,
        "reasons": [],
        "cited_ids": [],
        "supporting_evidence_ids": [],
        "contradicting_evidence_ids": [],
        "missing_evidence": [],
        "fact_hard": [],
        "error": "",
        "error_kind": "",
        "raw_text": "",
        "usage": {},
        "elapsed_ms": None,
        "call_mode": "",
        "temperature": None,
        "pii_sent": {"id": False, "phone": False, "account": False},
        "pii_in_chat_messages": {"id": False, "phone": False, "account": False},
        "pii_in_masked_payload": {"id": False, "phone": False, "account": False},
        "reached_vendor": False,
        "privacy_gate": "",
    }
    row.update(kwargs)
    return row


def _transport_row(template: dict, exc: BaseException, elapsed_ms: float | None) -> dict:
    kind = "network" if is_retryable(exc) else "api"
    row = dict(template)
    row.update(
        {
            "error": sanitize(str(exc)),
            "error_kind": kind,
            "elapsed_ms": elapsed_ms,
            "parse_ok": False,
            "pred": None,
            "blocked": False,
        }
    )
    return row


def parse_generic(text: str) -> dict:
    data = _extract_json_object(text)
    disp = str(data.get("disposition") or "").strip()
    if disp not in LABELS:
        raise ValueError(f"disposition 无法归入三档：{disp}")
    conf = data.get("confidence")
    confidence = None
    if conf not in (None, ""):
        confidence = float(conf)
        if not 0.0 <= confidence <= 1.0:
            confidence = None
    raw_reasons = data.get("reasons")
    if raw_reasons is None:
        raw_reasons = data.get("rationale") or []
    reasons = []
    for item in raw_reasons if isinstance(raw_reasons, list) else []:
        if isinstance(item, str):
            reasons.append({"text": item, "evidence_ids": []})
            continue
        if not isinstance(item, dict):
            continue
        reasons.append(
            {
                "text": str(item.get("text") or ""),
                "evidence_ids": [str(x) for x in (item.get("evidence_ids") or []) if str(x)],
            }
        )
    cited = [str(x) for x in (data.get("cited_ids") or []) if str(x)]
    missing = data.get("missing_evidence") or []
    if not isinstance(missing, list):
        missing = [str(missing)]
    return {
        "pred": disp,
        "confidence": confidence,
        "reasons": reasons,
        "cited_ids": cited,
        "missing_evidence": [str(x) for x in missing],
    }


def _reason_rows(decision: dict) -> list[dict]:
    rows = []
    for item in decision.get("rationale") or []:
        rows.append(
            {
                "text": str(item.get("text") or ""),
                "evidence_ids": [str(x) for x in (item.get("evidence_ids") or []) if str(x)],
            }
        )
    return rows


def evaluate_product(decision: dict, case: dict) -> dict:
    inputs = judge_inputs(case)
    allowed = set(inputs["allowed_evidence"])
    reasons = _reason_rows(decision)
    text = "\n".join(item["text"] for item in reasons)
    facts = fact_payload(case)
    hard = hard_fact_issues(fact_check(text, facts))
    predicate_facts = case_facts(
        transactions=inputs["transactions"],
        customer=inputs["customer"],
        account_id=inputs["alert"].get("account_id") or "",
    )
    verify = verify_judge(
        decision,
        allowed_evidence=allowed,
        facts=predicate_facts,
        case_id=str(case.get("case_id") or ""),
    )
    verify_hard = list(verify.get("hard_issues") or [])
    return {
        "reasons": reasons,
        "cited_ids": [],
        "supporting_evidence_ids": list(decision.get("supporting_evidence_ids") or []),
        "contradicting_evidence_ids": list(decision.get("contradicting_evidence_ids") or []),
        "missing_evidence": [str(x) for x in (decision.get("missing_evidence") or [])],
        "fact_hard": [{"token": item.get("token"), "kind": item.get("kind")} for item in hard],
        "verify_hard_n": len(verify_hard),
        "fact_hard_n": len(hard),
        "verify_hard": verify_hard,
        "fact_hard_full": hard,
    }


def _finish_generic(text: str, usage: dict, template: dict, case: dict) -> dict:
    row = dict(template)
    row["raw_text"] = _clip(text)
    row["usage"] = usage or {}
    try:
        parsed = parse_generic(text)
    except Exception as exc:
        row["parse_ok"] = False
        row["error_kind"] = "parse"
        row["parse_error"] = sanitize(str(exc))
        return row
    reasons = parsed["reasons"]
    hard = hard_fact_issues(fact_check("\n".join(item["text"] for item in reasons), fact_payload(case)))
    row.update(parsed)
    row["parse_ok"] = True
    row["blocked"] = False
    row["fact_hard"] = [{"token": item.get("token"), "kind": item.get("kind")} for item in hard]
    row["fact_hard_n"] = len(hard)
    return row


def _finish_product(data: dict, raw: str, usage: dict, template: dict, case: dict, arms: tuple[str, ...]) -> list[dict]:
    try:
        decision = normalize_judge(data, known_ids=set(judge_inputs(case)["allowed_evidence"]))
    except Exception as exc:
        rows = []
        for arm in arms:
            row = dict(template)
            row["arm"] = arm
            row["raw_text"] = _clip(raw)
            row["usage"] = usage or {}
            row["parse_ok"] = False
            row["error_kind"] = "parse"
            row["parse_error"] = sanitize(str(exc))
            row["blocked"] = False
            rows.append(row)
        return rows
    checked = evaluate_product(decision, case)
    pred = decision.get("disposition")
    rows = []
    for arm in arms:
        row = dict(template)
        row["arm"] = arm
        row["raw_text"] = _clip(raw)
        row["usage"] = usage or {}
        row["pred"] = pred if pred in LABELS else None
        row["parse_ok"] = pred in LABELS
        row["confidence"] = decision.get("confidence")
        row["blocked"] = arm_blocked(arm, checked["verify_hard"], checked["fact_hard_full"])
        for key in (
            "reasons",
            "cited_ids",
            "supporting_evidence_ids",
            "contradicting_evidence_ids",
            "missing_evidence",
            "fact_hard",
            "verify_hard_n",
            "fact_hard_n",
        ):
            row[key] = checked[key]
        rows.append(row)
    return rows


def _privacy_scan(case: dict) -> dict:
    inputs, context = _context(case)
    privacy = PrivacyMap()
    privacy.build_from_bundle(bundle_from(case))
    masked = json.dumps(privacy.mask_obj(context), ensure_ascii=False)
    return pii_flags(masked)


def _context(case: dict) -> tuple[dict, dict]:
    inputs = judge_inputs(case)
    context = build_judge_context(
        alert=inputs["alert"],
        customer=inputs["customer"],
        findings=inputs["findings"],
        transactions=inputs["transactions"],
        baseline=inputs["baseline"],
        kb_hits=inputs["kb_hits"],
        allowed_evidence=inputs["allowed_evidence"],
    )
    return inputs, context


def run_case(case: dict, *, arm: str, set_name: str, model: str, temperature: float, attack_kind: str, repeat: int) -> list[dict]:
    arms = ("A2", "A3") if arm == "A2A3" else (arm,)
    valid = case_valid_ids(case)
    template = _base_row(
        case_id=case["case_id"],
        source_case_id=case.get("_source_case_id") or case["case_id"],
        repeat=repeat,
        set=set_name,
        model=model,
        gold=case.get("gold"),
        attack_kind=attack_kind,
        temperature=temperature,
        valid_ids=valid,
        prompt_judge=prompt_version("judge"),
    )
    if arm in {"A0", "A1", "B"}:
        leaked = render_leaks(render_case(case))
        if leaked:
            raise RuntimeError(f"渲染泄漏 {leaked} case={case['case_id']}")
        messages = generic_messages(case, "A0" if arm == "A0" else "A1")
        template["pii_in_masked_payload"] = {"id": False, "phone": False, "account": False}
        started = time.perf_counter()
        tap = _Tap()
        try:
            with tap:
                with bypass_outbound_gate():
                    text, usage, mode = invoke_chat(
                        messages,
                        temperature=temperature,
                        model=model,
                        max_tokens=8000 if model == "deepseek-reasoner" else JUDGE_MAX_TOKENS,
                        reasoner=model == "deepseek-reasoner",
                    )
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            outbound = tap.messages or messages
            blob = _message_blob(outbound)
            template["pii_in_chat_messages"] = pii_flags(blob)
            template["pii_sent"] = pii_flags(blob)
            template["reached_vendor"] = True
            template["outbound_messages"] = _clip_messages(outbound)
            template["call_mode"] = mode
            template["elapsed_ms"] = elapsed
            template["arm"] = arm
            return [_finish_generic(text, usage, template, case)]
        except FatalAPIError:
            raise
        except PrivacyLeakError as exc:
            return [_privacy_row(template, arm, exc, tap.messages or messages, None, started)]
        except Exception as exc:
            template["arm"] = arm
            template["outbound_messages"] = _clip_messages(tap.messages or messages)
            template["pii_in_chat_messages"] = pii_flags(_message_blob(tap.messages or messages))
            return [_transport_row(template, exc, round((time.perf_counter() - started) * 1000, 1))]

    masked_flags = _privacy_scan(case)
    template["pii_in_masked_payload"] = masked_flags
    inputs, context = _context(case)
    started = time.perf_counter()
    tap = _Tap()
    try:
        with tap:
            if set_name == "stability" or case.get("user_suffix"):
                data, raw, usage, mode, outbound = _direct_product(
                    case,
                    inputs,
                    context,
                    model=model,
                    temperature=temperature,
                    suffix=str(case.get("user_suffix") or ""),
                )
            else:
                privacy = PrivacyMap()
                privacy.build_from_bundle(bundle_from(case))
                data, usage = enrich_judge(
                    db=None,
                    privacy=privacy,
                    prompt_kind=None,
                    alert=inputs["alert"],
                    customer=inputs["customer"],
                    findings=inputs["findings"],
                    transactions=inputs["transactions"],
                    baseline=inputs["baseline"],
                    kb_hits=inputs["kb_hits"],
                    allowed_evidence=inputs["allowed_evidence"],
                )
                raw = tap.text or ""
                mode = "enrich_judge"
                outbound = tap.messages
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        blob = _message_blob(outbound)
        template["pii_in_chat_messages"] = pii_flags(blob)
        template["pii_sent"] = pii_flags(blob)
        template["reached_vendor"] = True
        template["outbound_messages"] = _clip_messages(outbound)
        template["call_mode"] = mode
        template["elapsed_ms"] = elapsed
        if not raw and tap.messages:
            # enrich_judge 不回传原文；引用扫描还要看模型原文，从 tap 取助手侧做不到。
            # chat 返回值已解析进 data。原文留空时，编号仍从结构化字段收集。
            pass
        rows = _finish_product(data, raw, usage, template, case, arms)
        for row in rows:
            row["elapsed_ms"] = elapsed
            row["outbound_messages"] = template["outbound_messages"]
            row["pii_in_chat_messages"] = template["pii_in_chat_messages"]
            row["pii_sent"] = template["pii_sent"]
            row["pii_in_masked_payload"] = masked_flags
            row["reached_vendor"] = True
            row["call_mode"] = mode
        return rows
    except FatalAPIError:
        raise
    except PrivacyLeakError as exc:
        outbound = tap.messages
        return [
            _privacy_row(template, one, exc, outbound, masked_flags, started)
            for one in arms
        ]
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        rows = []
        for one in arms:
            row = dict(template)
            row["arm"] = one
            row["outbound_messages"] = _clip_messages(tap.messages)
            if tap.messages:
                row["pii_in_chat_messages"] = pii_flags(_message_blob(tap.messages))
            rows.append(_transport_row(row, exc, elapsed))
        return rows


def _privacy_row(template, arm, exc, messages, masked_flags, started) -> dict:
    row = dict(template)
    row["arm"] = arm
    row["error"] = sanitize(str(exc))
    row["error_kind"] = "privacy_gate"
    row["privacy_gate"] = "inspect_outbound" if "出站消息" in str(exc) else "assert_clean"
    row["blocked"] = False
    row["parse_ok"] = False
    row["reached_vendor"] = False
    row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    row["outbound_messages"] = _clip_messages(messages)
    if messages:
        row["pii_in_chat_messages"] = pii_flags(_message_blob(messages))
    if masked_flags is not None:
        row["pii_in_masked_payload"] = masked_flags
    return row


def _direct_product(case, inputs, context, *, model, temperature, suffix):
    privacy = PrivacyMap()
    privacy.build_from_bundle(bundle_from(case))
    payload = privacy.prepare_for_llm(context)
    user = json.dumps(payload, ensure_ascii=False)
    if suffix:
        user = user + "\n" + suffix
    kind = prompt_version("judge")
    messages = [
        {"role": "system", "content": PROMPTS[kind]},
        {"role": "user", "content": user},
    ]
    text, usage, mode = invoke_chat(
        messages,
        temperature=temperature,
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        reasoner=False,
    )
    data = _unmask_value(_extract_json_object(text), privacy)
    return data, text, usage, mode, messages


def run_job(
    *,
    arm: str,
    set_name: str,
    model: str,
    temperature: float | None,
    repeat: int | None,
    limit: int | None,
    attack_kind: str | None,
    no_write: bool,
    retry_errors: bool,
    store: Store | None = None,
) -> list[dict]:
    if set_name == "stability":
        temperature = 0.7
        repeat = 3 if repeat is None else repeat
    else:
        temperature = 0.0 if temperature is None else temperature
        repeat = 1 if repeat is None else repeat
    if arm == "B":
        model = model or "deepseek-reasoner"
    else:
        model = model or llm_model()
    own_store = store is None
    if store is None:
        store = Store(no_write=no_write, retry_errors=retry_errors)
    items = work_items(set_name, attack_kind, limit)
    written_arms = ("A2", "A3") if arm == "A2A3" else (arm,)
    produced: list[dict] = []
    print(
        f"开始 {arm} {set_name} model={model} n={len(items)} repeat={repeat} temperature={temperature} attack={attack_kind or '-'}",
        flush=True,
    )
    try:
        for index, (case, kind) in enumerate(items, start=1):
            for rep in range(repeat):
                if all(store.has(one, set_name, model, case["case_id"], rep) for one in written_arms):
                    continue
                try:
                    rows = run_case(
                        case,
                        arm=arm,
                        set_name=set_name,
                        model=model,
                        temperature=temperature,
                        attack_kind=kind,
                        repeat=rep,
                    )
                except FatalAPIError as exc:
                    print(f"鉴权或欠费，停止：{sanitize(str(exc))}", flush=True)
                    raise
                for row in rows:
                    store.append(row["arm"], set_name, model, row)
                    produced.append(row)
                flags = ",".join(
                    f"{row.get('arm')}:pred={row.get('pred')}:blocked={row.get('blocked')}" for row in rows
                )
                print(
                    f"{arm} {set_name} {index}/{len(items)} rep={rep} {case['case_id']} "
                    f"{flags} kind={rows[0].get('error_kind') or '-'}",
                    flush=True,
                )
                time.sleep(GAP_S)
    finally:
        if own_store:
            store.close()
    return produced


def smoke_issues(groups: dict[str, list[dict]]) -> list[str]:
    issues = []
    for name, rows in groups.items():
        if not rows:
            issues.append(f"{name} 没有记录")
            continue
        parsed = [row for row in rows if row.get("parse_ok")]
        if name != "attack-A3" and len(parsed) < 1:
            issues.append(f"{name} 没有解析成功的 JSON")
        if name.startswith("A0") or name.startswith("A1"):
            if any(row.get("blocked") for row in rows):
                issues.append(f"{name} 出现 blocked=True")
        if "A3" in name or name.startswith("A2A3"):
            if any("blocked" not in row for row in rows):
                issues.append(f"{name} 缺少 blocked")
            if not any(row.get("error_kind") == "privacy_gate" or "blocked" in row for row in rows):
                issues.append(f"{name} 没有闸门字段")
    return issues


def run_smoke() -> list[dict]:
    confirm_runtime()
    store = Store(no_write=True, retry_errors=False)
    groups: dict[str, list[dict]] = {}
    try:
        for arm, set_name in (("A0", "blind_struct"), ("A1", "blind_struct"), ("A2A3", "blind_struct")):
            groups[arm] = run_job(
                arm=arm,
                set_name=set_name,
                model=None,
                temperature=None,
                repeat=1,
                limit=5,
                attack_kind=None,
                no_write=True,
                retry_errors=False,
                store=store,
            )
        groups["attack-A1"] = run_job(
            arm="A1",
            set_name="attack",
            model=None,
            temperature=None,
            repeat=1,
            limit=1,
            attack_kind="fabricate_bait",
            no_write=True,
            retry_errors=False,
            store=store,
        )
        groups["attack-A3"] = run_job(
            arm="A3",
            set_name="attack",
            model=None,
            temperature=None,
            repeat=1,
            limit=1,
            attack_kind="pii_egress",
            no_write=True,
            retry_errors=False,
            store=store,
        )
    finally:
        store.close()
    issues = smoke_issues(groups)
    summary = {
        name: [
            {
                "case_id": row.get("case_id"),
                "pred": row.get("pred"),
                "blocked": row.get("blocked"),
                "parse_ok": row.get("parse_ok"),
                "error_kind": row.get("error_kind"),
                "privacy_gate": row.get("privacy_gate"),
                "parse_error": row.get("parse_error"),
                "error": row.get("error"),
                "raw_head": (row.get("raw_text") or "")[:240],
            }
            for row in rows
        ]
        for name, rows in groups.items()
    }
    print(json.dumps({"smoke": summary, "issues": issues}, ensure_ascii=False, indent=2), flush=True)
    if issues:
        raise SystemExit("冒烟未通过：" + "；".join(issues))
    return [row for rows in groups.values() for row in rows]


def run_full() -> None:
    confirm_runtime()
    ensure_inputs()
    store = Store(no_write=False, retry_errors=False)
    try:
        for arm, set_name, model in FULL_JOBS:
            run_job(
                arm=arm,
                set_name=set_name,
                model=model,
                temperature=None,
                repeat=None,
                limit=None,
                attack_kind=None,
                no_write=False,
                retry_errors=False,
                store=store,
            )
    finally:
        store.close()
        from experiments.vs_generic.score import write_outputs

        wrote = write_outputs()
        print(json.dumps({"aggregated": True, "preserved_keys": len(wrote["preserved_keys"])}, ensure_ascii=False), flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["A0", "A1", "A2A3", "A3", "B"])
    parser.add_argument("--set", choices=["blind", "blind_struct", "attack", "stability", "b"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--repeat", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--attack-kind", default=None)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--suite", choices=["smoke", "full"], default=None)
    args = parser.parse_args()
    try:
        if args.suite == "smoke":
            run_smoke()
            return
        if args.suite == "full":
            run_full()
            return
        if not args.arm or not args.set:
            raise SystemExit("需要 --arm 和 --set，或 --suite")
        confirm_runtime()
        rows = run_job(
            arm=args.arm,
            set_name=args.set,
            model=args.model,
            temperature=args.temperature,
            repeat=args.repeat,
            limit=args.limit,
            attack_kind=args.attack_kind,
            no_write=args.no_write,
            retry_errors=args.retry_errors,
        )
        if args.no_write:
            brief = [
                {
                    "arm": row.get("arm"),
                    "case_id": row.get("case_id"),
                    "pred": row.get("pred"),
                    "blocked": row.get("blocked"),
                    "parse_ok": row.get("parse_ok"),
                    "error_kind": row.get("error_kind"),
                    "privacy_gate": row.get("privacy_gate"),
                }
                for row in rows
            ]
            print(json.dumps(brief, ensure_ascii=False, indent=2), flush=True)
    except FatalAPIError as exc:
        from experiments.vs_generic.score import write_outputs

        try:
            write_outputs()
        except Exception as write_exc:
            print(f"汇总失败 {sanitize(str(write_exc))}", flush=True)
        raise SystemExit(f"已停止并尽量汇总：{sanitize(str(exc))}") from None


if __name__ == "__main__":
    main()
