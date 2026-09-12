"""Benchmark v3：独立组合采样集（规则层同构）+ 产品 Judge 流水线。

必须：
- 直接调用产品 `enrich_judge(db=None)`（prompt 由产品 `prompt_version("judge")` 决定）
- 经 normalize_judge → verify_judge → apply_guardrails
- 原始输出落盘 runs/<timestamp>.jsonl
- 解析失败单独计数，不并入 observe
- 分组指标 + 无信息/关键词基线 + confidence 直方图 + observe 缺材料比例

口径：实验对照，不是生产准确率；须人工签发。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app import llm as llm_mod  # noqa: E402
from app.decision import apply_guardrails, normalize_judge, verify_judge  # noqa: E402
from app.llm import enrich_judge, llm_model, require_api_key  # noqa: E402
from app.metrics_lib import LABELS, classification_report, evidence_prf  # noqa: E402
from app.prompts import prompt_version  # noqa: E402

BENCH_DIR = Path(__file__).parent / "benchmark"
RUNS_DIR = BENCH_DIR / "runs"

SET_FILES = {
    "v3": "independent_set.json",
    "independent": "independent_set.json",
    "nopolarity": "independent_set_nopolarity.json",
    "blind": "blind_set.json",
}

CONFIDENCE_BINS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01))
NARRATIVE_PREFIX = "IX-"


def load_split(name: str) -> dict:
    return json.loads((BENCH_DIR / name).read_text(encoding="utf-8"))


def _keyword_baseline_pred(case: dict) -> str:
    """极弱关键词规则，仅作无信息对照，不是产品规则引擎。"""
    text = " ".join(
        [
            case.get("vignette", {}).get("alert_type") or "",
            case.get("vignette", {}).get("summary") or "",
            " ".join(e.get("text") or "" for e in case.get("vignette", {}).get("candidate_evidence") or []),
        ]
    )
    report_kw = ("ATM", "取现", "回流", "闭环", "开票", "虚拟资产", "兑换", "过桥", "空壳", "众筹", "分层")
    exclude_kw = ("工资", "发薪", "赔付", "保单", "财政", "补贴", "监管账户", "网签")
    observe_kw = ("缺", "不齐", "待核", "补证", "材料")
    if any(k in text for k in report_kw):
        return "suggest_report"
    if any(k in text for k in exclude_kw) and not any(k in text for k in observe_kw):
        return "exclude"
    if any(k in text for k in observe_kw):
        return "observe"
    return "observe"


def offline_baselines(cases: list[dict]) -> dict:
    y_true = [c["gold"] for c in cases]
    always = ["suggest_report"] * len(cases)
    keyword = [_keyword_baseline_pred(c) for c in cases]
    return {
        "always_suggest_report": classification_report(y_true, always),
        "keyword_match": classification_report(y_true, keyword),
        "note": "无信息/弱规则基线，用于锚定真实模型分数高低；不是产品准确率。",
    }


def per_tag_report(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("pred") in LABELS:
            grouped[r.get("tag") or "unknown"].append(r)
    out = {}
    for tag, items in sorted(grouped.items()):
        y_true = [x["gold"] for x in items]
        y_pred = [x["pred"] for x in items]
        rep = classification_report(y_true, y_pred)
        out[tag] = {
            "n": len(items),
            "macro_f1": rep["macro_f1"],
            "accuracy": rep["accuracy"],
            "gold": items[0]["gold"] if items else "",
            "confusion_matrix": rep["confusion_matrix"],
        }
    return out


def _case_to_judge_inputs(case: dict) -> dict:
    """独立集 v3 已按产品 bundle 结构落盘：这里只做取值，不再拼装任何非产品字段。"""
    vig = case["vignette"]
    txs = list(vig.get("transactions") or [])
    findings = list(vig.get("findings") or [])
    customer = dict(vig.get("customer") or {})
    customer.setdefault("id", f"C-{case['case_id']}")
    alert = dict(vig.get("alert") or {})
    alert.setdefault("id", case["case_id"])
    alert.setdefault("alert_type", vig.get("alert_type") or "")
    alert.setdefault("upstream", "independent-benchmark")
    allowed = list(vig.get("allowed_evidence") or [])
    if not allowed:
        allowed = sorted(
            {t["id"] for t in txs if t.get("id")}
            | {e["id"] for e in vig.get("candidate_evidence") or []}
            | {f_id for f in findings for f_id in f.get("evidence_ids") or []}
        )
    return {
        "alert": alert,
        "customer": customer,
        "findings": findings,
        "transactions": txs,
        "baseline": dict(vig.get("baseline") or {}),
        "kb_hits": list(vig.get("kb_hits") or []),
        "allowed_evidence": allowed,
        "watch_hits": list(vig.get("watch_hits") or []),
    }


class _ChatRecorder:
    """包一层产品 chat，只为把 raw_text 落盘；不改变请求内容。"""

    def __init__(self) -> None:
        self.last_text = ""
        self.last_usage: dict = {}
        self._orig = llm_mod.chat

    def __enter__(self) -> "_ChatRecorder":
        def _wrapped(messages, **kwargs):
            text, usage = self._orig(messages, **kwargs)
            self.last_text, self.last_usage = text, usage
            return text, usage

        llm_mod.chat = _wrapped
        return self

    def __exit__(self, *exc) -> None:
        llm_mod.chat = self._orig


def _judge_kwargs(prompt_kind: str | None) -> dict:
    return {"prompt_kind": prompt_kind} if prompt_kind else {}


def _predict_one(case: dict, *, prompt_kind: str | None = None) -> dict:
    """走产品 Judge 契约：enrich_judge(db=None) → normalize → verify → guardrails。"""
    inputs = _case_to_judge_inputs(case)
    allowed_set = set(inputs["allowed_evidence"])
    raw_text = ""
    usage: dict = {}
    parse_ok = False
    verify: dict = {}
    guardrails: dict = {}
    decision: dict = {}
    pred = None
    support_ids: list[str] = []
    contra_ids: list[str] = []
    error = ""
    with _ChatRecorder() as rec:
        try:
            raw, usage = enrich_judge(
                db=None,
                alert=inputs["alert"],
                customer=inputs["customer"],
                findings=inputs["findings"],
                transactions=inputs["transactions"],
                baseline=inputs["baseline"],
                kb_hits=inputs["kb_hits"],
                allowed_evidence=inputs["allowed_evidence"],
                **_judge_kwargs(prompt_kind),
            )
            raw_text = rec.last_text
            decision = normalize_judge(raw, known_ids=allowed_set)
            parse_ok = True
            verify = verify_judge(decision, allowed_evidence=allowed_set)
            guardrails = apply_guardrails(decision, watch_hits=inputs["watch_hits"], fact_issues=None)
            pred = guardrails["final_conclusion"]
            support_ids = [x for x in (decision.get("supporting_evidence_ids") or []) if x in allowed_set]
            contra_ids = [x for x in (decision.get("contradicting_evidence_ids") or []) if x in allowed_set]
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:400]
            raw_text = raw_text or rec.last_text
            usage = usage or rec.last_usage

    return {
        "case_id": case["case_id"],
        "tag": case.get("tag") or "",
        "gold": case["gold"],
        "pred": pred,
        "proposed": decision.get("disposition") if decision else None,
        "confidence": decision.get("confidence") if decision else None,
        "missing_evidence": list(decision.get("missing_evidence") or []) if decision else [],
        "sanitized_missing_evidence": list(decision.get("sanitized_missing_evidence") or []) if decision else [],
        "rationale_n": len(decision.get("rationale") or []) if decision else 0,
        "parse_ok": parse_ok,
        "verify_passed": bool(verify.get("passed")) if verify else False,
        "verify_issues": verify.get("issues") if verify else [],
        "guardrails_overridden": bool(guardrails.get("overridden")) if guardrails else False,
        "gold_support_ids": list(case.get("gold_support_ids") or case.get("gold_evidence_ids") or []),
        "gold_contradict_ids": list(case.get("gold_contradict_ids") or []),
        "pred_support_ids": support_ids,
        "pred_contradict_ids": contra_ids,
        "rule_finding_codes": list(case.get("rule_finding_codes") or []),
        "annotation_reason": case.get("annotation_reason") or "",
        "raw_text": (raw_text or "")[:4000],
        "usage": usage,
        "finish_reason": (usage or {}).get("finish_reason"),
        "completion_tokens": (usage or {}).get("completion_tokens"),
        "error": error,
    }


def confidence_report(rows: list[dict]) -> dict:
    """confidence 是否真在变：直方图 + 去重值数 + 标准差 + 各 gold 档均值。"""
    vals = [float(r["confidence"]) for r in rows if isinstance(r.get("confidence"), (int, float))]
    hist = {}
    for lo, hi in CONFIDENCE_BINS:
        label = f"[{lo:.1f},{min(hi, 1.0):.1f}{']' if hi > 1 else ')'}"
        hist[label] = sum(1 for v in vals if lo <= v < hi)
    by_gold: dict[str, list[float]] = defaultdict(list)
    by_pred: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        v = r.get("confidence")
        if isinstance(v, (int, float)):
            by_gold[r["gold"]].append(float(v))
            if r.get("pred") in LABELS:
                by_pred[r["pred"]].append(float(v))
    return {
        "n": len(vals),
        "histogram": hist,
        "distinct_values": len({round(v, 2) for v in vals}),
        "mean": round(statistics.fmean(vals), 4) if vals else None,
        "stdev": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
        "mean_by_gold": {k: round(statistics.fmean(v), 4) for k, v in sorted(by_gold.items())},
        "mean_by_pred": {k: round(statistics.fmean(v), 4) for k, v in sorted(by_pred.items())},
        "value_counts_top": dict(Counter(round(v, 2) for v in vals).most_common(6)),
    }


def missing_evidence_report(rows: list[dict]) -> dict:
    """observe 预测中带非空 missing_evidence 的比例（judge_v3 要求 observe 必列待补材料）。"""
    out: dict = {}
    for label in LABELS:
        items = [r for r in rows if r.get("pred") == label]
        with_missing = [r for r in items if r.get("missing_evidence")]
        out[label] = {
            "n": len(items),
            "with_missing_n": len(with_missing),
            "with_missing_ratio": round(len(with_missing) / len(items), 4) if items else None,
            "avg_missing_len": round(statistics.fmean(len(r["missing_evidence"]) for r in items), 3) if items else None,
        }
    observe = out.get("observe") or {}
    return {
        "by_pred": out,
        "observe_with_missing_ratio": observe.get("with_missing_ratio"),
        "sanitized_id_like_n": sum(len(r.get("sanitized_missing_evidence") or []) for r in rows),
    }


def _narrative_only(ids: list[str]) -> list[str]:
    return [x for x in ids if str(x).startswith(NARRATIVE_PREFIX)]


def evaluate_independent(
    *,
    limit: int | None = None,
    sleep_s: float = 0.0,
    prompt_kind: str | None = None,
    set_name: str = "v3",
) -> dict:
    os.environ.pop("HUICHA_LLM_STUB", None)
    require_api_key()
    prompt_used = prompt_kind or prompt_version("judge")
    set_file = SET_FILES.get(set_name, set_name)
    if not set_file.endswith(".json"):
        set_file = f"{set_file}.json"
    payload = load_split(set_file)
    cases = list(payload.get("cases") or [])
    if limit is not None:
        cases = cases[: max(0, limit)]
    if not cases:
        raise RuntimeError(f"{set_file} 为空，请先运行 build_independent_set.py --variant …")

    baselines = offline_baselines(cases)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    variant = payload.get("variant") or set_name
    run_path = RUNS_DIR / f"{ts}_{variant}_{prompt_used}.jsonl"

    rows: list[dict] = []
    call_errors = 0
    parse_failures = 0
    with run_path.open("w", encoding="utf-8") as fh:
        for i, case in enumerate(cases, start=1):
            row = _predict_one(case, prompt_kind=prompt_kind)
            if row.get("error") and not row.get("parse_ok"):
                call_errors += 1
            if not row.get("parse_ok") or row.get("pred") not in LABELS:
                parse_failures += 1
                row["pred"] = None
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
            if i % 20 == 0:
                print(
                    f"progress {i}/{len(cases)} parse_failures={parse_failures} call_errors={call_errors}",
                    flush=True,
                )
            if sleep_s:
                time.sleep(sleep_s)

    scored = [r for r in rows if r.get("pred") in LABELS]
    y_true = [r["gold"] for r in scored]
    y_pred = [r["pred"] for r in scored]
    clf = classification_report(y_true, y_pred) if scored else classification_report([], [])
    # 证据 P/R 只在叙事项（IX-）上计算：gold 只标注叙事项，TX/KB 引用单独统计引用率。
    support_ev = evidence_prf(
        [_narrative_only(r["pred_support_ids"]) for r in scored],
        [r["gold_support_ids"] for r in scored],
    )
    contra_ev = evidence_prf(
        [_narrative_only(r["pred_contradict_ids"]) for r in scored],
        [r["gold_contradict_ids"] for r in scored],
    )
    tx_cite_rate = (
        round(
            sum(1 for r in scored if any(str(x).startswith("TX-") for x in r["pred_support_ids"] + r["pred_contradict_ids"]))
            / len(scored),
            4,
        )
        if scored
        else None
    )
    return {
        "label": "独立集 / 真实模型 / 产品 Judge 流水线",
        "protocol": "enrich_judge(db=None) → normalize_judge → verify_judge → apply_guardrails",
        "prompt": prompt_used,
        "split": payload.get("split") or "independent",
        "variant": variant,
        "set_file": set_file,
        "model": llm_model(),
        "n": len(rows),
        "n_unique_dataset": payload.get("n_unique"),
        "n_scored": len(scored),
        "parse_failures": parse_failures,
        "call_errors": call_errors,
        "verify_pass_rate": round(
            sum(1 for r in scored if r.get("verify_passed")) / len(scored), 4
        )
        if scored
        else 0.0,
        "source": payload.get("source"),
        "caveat": payload.get("caveat"),
        "run_log": run_path.relative_to(ROOT).as_posix(),
        "baselines": baselines,
        "classification": clf,
        "by_tag": per_tag_report(rows),
        "evidence_support": support_ev,
        "evidence_contradict": contra_ev,
        "evidence_precision": support_ev.get("evidence_precision"),
        "evidence_recall": support_ev.get("evidence_recall"),
        "evidence_scope": "仅叙事项 IX- 编号参与 P/R；TX-/KB- 引用不计入",
        "tx_cite_rate": tx_cite_rate,
        "confidence": confidence_report(scored),
        "missing_evidence": missing_evidence_report(scored),
        "confusion_matrix": clf.get("confusion_matrix"),
        "macro_f1": clf.get("macro_f1"),
        "observe_pred_rate": round(sum(1 for r in scored if r.get("pred") == "observe") / len(scored), 4) if scored else None,
        "honesty": (
            "不是生产准确率；须人工签发。"
            "本协议已去除标签泄漏并走产品 Judge 契约（enrich_judge 直调）；仍为合成 vignette。"
        ),
        "legacy_note": (
            "v1 结果（Macro-F1≈0.69）因 n_unique≈10、标签泄漏、自写 prompt 已降级，"
            "不得与本协议数字混比。"
        ),
    }


def framework_status() -> dict:
    golden = load_split("golden_set.json")
    test = load_split("test_set.json")
    independent = load_split("independent_set.json")
    cases = independent.get("cases") or []
    fps = {c.get("fingerprint") for c in cases if c.get("fingerprint")}
    # 兼容旧集：无 fingerprint 时按内容估唯一数
    if not fps and cases:
        import hashlib

        for c in cases:
            vig = c.get("vignette") or {}
            blob = json.dumps(
                {
                    "a": vig.get("alert_type"),
                    "s": vig.get("summary"),
                    "e": [x.get("text") for x in vig.get("candidate_evidence") or []],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            fps.add(hashlib.sha256(blob.encode()).hexdigest())
    baselines = offline_baselines(cases) if cases else {}
    return {
        "golden_n": len(golden.get("cases") or []),
        "test_n": len(test.get("cases") or []),
        "independent_n": len(cases),
        "independent_n_unique": len(fps),
        "independent_source": independent.get("source"),
        "baselines": {
            "always_suggest_report_macro_f1": (baselines.get("always_suggest_report") or {}).get("macro_f1"),
            "keyword_match_macro_f1": (baselines.get("keyword_match") or {}).get("macro_f1"),
        },
        "note": golden.get("caveat"),
        "independent_caveat": independent.get("caveat"),
        "hint": "真实评估: python experiments/benchmark.py --real",
        "protocol": f"product {prompt_version('judge')} pipeline (enrich_judge direct)",
    }


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v) if v is not None else "—"


def render_md_section(result: dict) -> list[str]:
    cm = (result.get("confusion_matrix") or {}).get("matrix") or {}
    labels = (result.get("confusion_matrix") or {}).get("labels") or list(LABELS)
    base = result.get("baselines") or {}
    conf = result.get("confidence") or {}
    miss = result.get("missing_evidence") or {}
    lines = [
        f"## 独立集 / 真实模型（v3 协议 · prompt={result.get('prompt')}）",
        "",
        f"- 协议：`{result.get('protocol')}` · prompt=`{result.get('prompt')}`",
        f"- 标注集：`independent_set.json`（n={result['n']}，n_unique={result.get('n_unique_dataset')}，source={result.get('source')}）",
        f"- 模型：`{result.get('model')}`（真实调用）",
        f"- 计分条数：{result.get('n_scored')}（parse_failures={result.get('parse_failures')}，call_errors={result.get('call_errors')}）",
        f"- verify 通过率：{result.get('verify_pass_rate')}",
        f"- Macro-F1：**{result.get('macro_f1')}**",
        f"- Evidence 支持侧 P/R：**{result.get('evidence_precision')} / {result.get('evidence_recall')}**（{result.get('evidence_scope')}）",
        f"- Evidence 反证侧 P/R：**{(result.get('evidence_contradict') or {}).get('evidence_precision')} / {(result.get('evidence_contradict') or {}).get('evidence_recall')}**",
        f"- 引用过 TX- 编号的样本比例：{result.get('tx_cite_rate')}",
        f"- 基线 Macro-F1：always_report={(base.get('always_suggest_report') or {}).get('macro_f1')} · keyword={(base.get('keyword_match') or {}).get('macro_f1')}",
        f"- 原始输出：`{result.get('run_log')}`",
        f"- 口径：{result.get('honesty')}",
        f"- 旧版说明：{result.get('legacy_note')}",
        "",
        "### 混淆矩阵（行=gold，列=pred；仅 parse 成功样本）",
        "",
        "| gold \\ pred | " + " | ".join(labels) + " |",
        "| --- | " + " | ".join(["---"] * len(labels)) + " |",
    ]
    for a in labels:
        row = cm.get(a) or {}
        lines.append("| " + a + " | " + " | ".join(str(row.get(b, 0)) for b in labels) + " |")
    lines.extend(["", "### confidence 分布", ""])
    hist = conf.get("histogram") or {}
    lines.append("| 区间 | " + " | ".join(hist.keys()) + " |")
    lines.append("| --- | " + " | ".join(["---"] * len(hist)) + " |")
    lines.append("| 条数 | " + " | ".join(str(v) for v in hist.values()) + " |")
    lines.extend(
        [
            "",
            f"- 去重取值数={conf.get('distinct_values')} · mean={conf.get('mean')} · stdev={conf.get('stdev')} · min/max={conf.get('min')}/{conf.get('max')}",
            f"- 按 gold 均值：`{json.dumps(conf.get('mean_by_gold') or {}, ensure_ascii=False)}` · 按 pred 均值：`{json.dumps(conf.get('mean_by_pred') or {}, ensure_ascii=False)}`",
            f"- 最常见取值：`{json.dumps(conf.get('value_counts_top') or {}, ensure_ascii=False)}`",
            "",
            "### missing_evidence 契约",
            "",
            f"- observe 预测中带非空 missing_evidence 的比例：**{miss.get('observe_with_missing_ratio')}**",
            f"- 按 pred：`{json.dumps(miss.get('by_pred') or {}, ensure_ascii=False)}`",
            f"- 被 sanitize 掉的编号样条目数：{miss.get('sanitized_id_like_n')}",
            "",
            "### 按 tag 分组 Macro-F1",
            "",
        ]
    )
    for tag, info in (result.get("by_tag") or {}).items():
        lines.append(
            f"- `{tag}` (gold={info.get('gold')}, n={info.get('n')}): macro_f1={info.get('macro_f1')}, acc={info.get('accuracy')}"
        )
    lines.extend(
        [
            "",
            f"- per_class：`{json.dumps((result.get('classification') or {}).get('per_class') or {}, ensure_ascii=False)}`",
            f"- caveat：{result.get('caveat')}",
            "",
        ]
    )
    return lines


ABLATION_METRICS = [
    ("macro_f1", "Macro-F1"),
    ("accuracy", "Accuracy"),
    ("evidence_precision", "Evidence P（支持侧）"),
    ("evidence_recall", "Evidence R（支持侧）"),
    ("verify_pass_rate", "verify 通过率"),
    ("parse_failures", "parse_failures"),
    ("confidence_distinct", "confidence 去重取值数"),
    ("confidence_stdev", "confidence 标准差"),
    ("observe_with_missing_ratio", "observe 带 missing 比例"),
    ("exclude_recall", "exclude 召回"),
    ("observe_recall", "observe 召回"),
    ("suggest_report_recall", "suggest_report 召回"),
    ("observe_pred_rate", "observe 预测率"),
]


def _flatten_for_ablation(result: dict) -> dict:
    per_class = (result.get("classification") or {}).get("per_class") or {}
    conf = result.get("confidence") or {}
    return {
        "prompt": result.get("prompt"),
        "run_log": result.get("run_log"),
        "n_scored": result.get("n_scored"),
        "macro_f1": result.get("macro_f1"),
        "accuracy": (result.get("classification") or {}).get("accuracy"),
        "evidence_precision": result.get("evidence_precision"),
        "evidence_recall": result.get("evidence_recall"),
        "verify_pass_rate": result.get("verify_pass_rate"),
        "parse_failures": result.get("parse_failures"),
        "confidence_distinct": conf.get("distinct_values"),
        "confidence_stdev": conf.get("stdev"),
        "observe_with_missing_ratio": (result.get("missing_evidence") or {}).get("observe_with_missing_ratio"),
        "exclude_recall": (per_class.get("exclude") or {}).get("recall"),
        "observe_recall": (per_class.get("observe") or {}).get("recall"),
        "suggest_report_recall": (per_class.get("suggest_report") or {}).get("recall"),
        "observe_pred_rate": result.get("observe_pred_rate"),
        "confusion_matrix": (result.get("confusion_matrix") or {}).get("matrix"),
    }


def build_ablation(runs: dict[str, dict]) -> dict | None:
    """同一独立集上不同 judge prompt 的并排对比；只有 ≥2 个 prompt 时才有意义。"""
    if len(runs) < 2:
        return None
    ordered = sorted(runs.keys())
    return {
        "note": "同一 independent_set.json、同一模型、同一后处理；唯一变量为 judge prompt 版本。",
        "prompts": ordered,
        "rows": {p: _flatten_for_ablation(runs[p]) for p in ordered},
    }


def render_ablation_md(ablation: dict) -> list[str]:
    prompts = ablation["prompts"]
    lines = [
        "## 消融：judge prompt 版本对比（同一独立集）",
        "",
        f"- {ablation['note']}",
        "",
        "| 指标 | " + " | ".join(f"`{p}`" for p in prompts) + " |",
        "| --- | " + " | ".join(["---"] * len(prompts)) + " |",
    ]
    for key, label in ABLATION_METRICS:
        lines.append(f"| {label} | " + " | ".join(_fmt(ablation["rows"][p].get(key)) for p in prompts) + " |")
    lines.append("")
    for p in prompts:
        cm = ablation["rows"][p].get("confusion_matrix") or {}
        lines.append(f"- `{p}` 混淆矩阵（行=gold）：`{json.dumps(cm, ensure_ascii=False)}` · 原始输出 `{ablation['rows'][p].get('run_log')}`")
    lines.append("")
    return lines


def render_validity_md(comparison: dict) -> list[str]:
    cells = comparison.get("cells") or {}
    if not cells:
        return []
    lines = ["## 有效性消融（主集 / 去极性 / 盲区）", "", f"- {comparison.get('note')}", ""]
    keys = [
        ("macro_f1", "Macro-F1"),
        ("exclude_recall", "exclude 召回"),
        ("suggest_report_recall", "suggest_report 召回"),
        ("observe_pred_rate", "observe 预测率"),
    ]
    for source, runs in cells.items():
        lines.append(f"### `{source}`")
        lines.append("")
        prompts = sorted(runs)
        lines.append("| 指标 | " + " | ".join(f"`{p}`" for p in prompts) + " |")
        lines.append("| --- | " + " | ".join(["---"] * len(prompts)) + " |")
        for key, label in keys:
            lines.append(f"| {label} | " + " | ".join(_fmt(runs[p].get(key)) for p in prompts) + " |")
        lines.append("")
    return lines


def update_results_md(result: dict, ablation: dict | None = None) -> None:
    md_path = Path(__file__).parent / "RESULTS.md"
    json_path = Path(__file__).parent / "RESULTS.json"
    text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    marker = "## 独立集 / 真实模型"
    stub_tail = (
        "## 能力指标占位（规则同源 stub）\n"
        "- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。\n"
        "- 上节为独立 vignette × 产品 Judge 的实验数字，禁止与 stub 机制验证混写成产品准确率。\n"
    )
    section = "\n".join(render_md_section(result))
    if ablation:
        section += "\n" + "\n".join(render_ablation_md(ablation))
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        extra = []
        for key in ("independent_ablation", "nopolarity_ablation", "blind_ablation"):
            if key in data and data[key] and key == "independent_ablation" and ablation:
                continue
            if data.get(key):
                extra.extend(render_ablation_md(data[key]))
        if data.get("validity_comparison"):
            extra.extend(render_validity_md(data["validity_comparison"]))
        if extra:
            section += "\n" + "\n".join(extra)
    if marker in text:
        head, _, _rest = text.partition(marker)
        base = head.rstrip() + "\n\n"
    elif "## 5. 能力指标" in text:
        base = text.split("## 5. 能力指标")[0].rstrip() + "\n\n"
    else:
        base = text.rstrip() + "\n\n"
    md_path.write_text(base + section + "\n" + stub_tail, encoding="utf-8")


RESULT_KEEP_KEYS = [
    "label",
    "protocol",
    "prompt",
    "split",
    "variant",
    "set_file",
    "model",
    "n",
    "n_unique_dataset",
    "n_scored",
    "parse_failures",
    "call_errors",
    "verify_pass_rate",
    "source",
    "macro_f1",
    "evidence_precision",
    "evidence_recall",
    "evidence_scope",
    "tx_cite_rate",
    "evidence_support",
    "evidence_contradict",
    "confidence",
    "missing_evidence",
    "confusion_matrix",
    "baselines",
    "by_tag",
    "run_log",
    "honesty",
    "caveat",
    "legacy_note",
    "classification",
    "observe_pred_rate",
]


def update_results_json(result: dict) -> dict | None:
    """按 source×prompt 分槽保存，换集不覆盖旧消融。返回当前 source 的 prompt 消融（若有）。"""
    path = Path(__file__).parent / "RESULTS.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if "independent_real_model" in data and "independent_real_model_v1_deprecated" not in data:
        old = data["independent_real_model"]
        old["deprecated"] = True
        old["deprecation_reason"] = (
            "v1：n_unique≈10、标签泄漏、自写 SYSTEM 贴合测试集、未走产品 Judge；"
            "仅作流水线打通记录，不得解释为模型能力。"
        )
        data["independent_real_model_v1_deprecated"] = old
    slim = {k: result[k] for k in RESULT_KEEP_KEYS if k in result}
    src = str(result.get("source") or "unknown")
    by_source = data.get("runs_by_source") or {}
    if not by_source and data.get("independent_real_model_runs"):
        by_source = {"narrative_vignette_v3_rules_layer": dict(data["independent_real_model_runs"])}
    src_runs = dict(by_source.get(src) or {})
    src_runs[str(result.get("prompt"))] = slim
    by_source[src] = src_runs
    data["runs_by_source"] = by_source
    data["independent_real_model"] = slim
    if src == "narrative_vignette_v3_rules_layer":
        data["independent_real_model_runs"] = src_runs
        ablation = build_ablation(src_runs)
        if ablation:
            data["independent_ablation"] = ablation
    else:
        ablation = build_ablation(src_runs)
        slot = {
            "narrative_vignette_v3_rules_layer_nopolarity": "nopolarity_ablation",
            "narrative_vignette_blind_holdout": "blind_ablation",
        }.get(src)
        if slot and ablation:
            data[slot] = ablation
    data["validity_comparison"] = {
        "note": "跨数据集对比：v3 主集 / 去极性 / 盲区 hold-out；同一模型与后处理。",
        "cells": {
            source: {p: _flatten_for_ablation(run) for p, run in runs.items()}
            for source, runs in sorted(by_source.items())
        },
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return ablation


def main() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="独立集上真实调用产品 Judge")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--baselines-only", action="store_true", help="只算离线基线，不调模型")
    parser.add_argument(
        "--prompt",
        default=None,
        help="覆盖 judge prompt 版本（如 judge_v2 / judge_v3）；默认用产品 prompt_version('judge')。仅作消融，不改产品默认值。",
    )
    parser.add_argument("--no-write", action="store_true", help="不写 RESULTS.json / RESULTS.md（试跑用）")
    parser.add_argument("--rerender", action="store_true", help="不调模型，用 RESULTS.json 现有结果重渲染 RESULTS.md")
    parser.add_argument(
        "--set",
        dest="set_name",
        default="v3",
        help="数据集：v3 / nopolarity / blind，或 json 文件名。默认 independent_set.json",
    )
    args = parser.parse_args()
    if args.rerender:
        data = json.loads((Path(__file__).parent / "RESULTS.json").read_text(encoding="utf-8"))
        latest = data.get("independent_real_model") or {}
        runs = data.get("independent_real_model_runs") or {}
        ablation = build_ablation(runs)
        if ablation:
            data["independent_ablation"] = ablation
            (Path(__file__).parent / "RESULTS.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        update_results_md(latest, ablation)
        print(json.dumps({"rerendered": True, "prompts": list(runs.keys())}, ensure_ascii=False))
        return latest
    if args.baselines_only:
        set_file = SET_FILES.get(args.set_name, args.set_name)
        if not str(set_file).endswith(".json"):
            set_file = f"{set_file}.json"
        payload = load_split(set_file)
        out = {
            "n": len(payload.get("cases") or []),
            "n_unique": payload.get("n_unique"),
            "baselines": offline_baselines(payload.get("cases") or []),
            "source": payload.get("source"),
            "set": set_file,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    if not args.real:
        out = framework_status()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    result = evaluate_independent(limit=args.limit, prompt_kind=args.prompt, set_name=args.set_name)
    if not args.no_write:
        ablation = update_results_json(result)
        update_results_md(result, ablation)
    printable = {k: v for k, v in result.items() if k != "by_tag"}
    printable["by_tag_n"] = len(result.get("by_tag") or {})
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
