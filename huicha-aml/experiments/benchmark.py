"""Benchmark v2：独立组合采样集 + 产品 Judge 流水线。

必须：
- 使用 prompts.judge_v2 + enrich_judge
- 经 normalize_judge → verify_judge → apply_guardrails
- 原始输出落盘 runs/<timestamp>.jsonl
- 解析失败单独计数，不并入 observe
- 分组指标 + 无信息/关键词基线

口径：实验对照，不是生产准确率；须人工签发。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.decision import apply_guardrails, normalize_judge, verify_judge  # noqa: E402
from app.llm import JUDGE_MAX_TOKENS, _parse_model_json, chat, llm_model, require_api_key  # noqa: E402
from app.metrics_lib import LABELS, classification_report, evidence_prf  # noqa: E402
from app.prompts import PROMPTS  # noqa: E402

BENCH_DIR = Path(__file__).parent / "benchmark"
RUNS_DIR = BENCH_DIR / "runs"


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
    vig = case["vignette"]
    evidences = list(vig.get("candidate_evidence") or [])
    allowed = [e["id"] for e in evidences]
    for t in vig.get("transactions") or []:
        if t.get("id") and t["id"] not in allowed:
            allowed.append(t["id"])
    findings = list(vig.get("findings") or [])
    if not findings:
        findings = [
            {
                "title": f"材料摘录{i + 1}",
                "detail": e.get("text") or "",
                "evidence_ids": [e["id"]],
                "code": "vignette-fact",
                "polarity": "context",
            }
            for i, e in enumerate(evidences)
        ]
    customer = dict(vig.get("customer") or {})
    customer.setdefault("id", f"C-{case['case_id']}")
    alert = {
        "id": case["case_id"],
        "alert_type": vig.get("alert_type") or "",
        "upstream": "independent-benchmark-v2",
        "account_id": f"ACC-{case['case_id']}",
        "created_at": "2026-09-12 10:00:00",
        "title": vig.get("summary") or "",
    }
    return {
        "alert": alert,
        "customer": customer,
        "findings": findings,
        "transactions": list(vig.get("transactions") or []),
        "baseline": dict(vig.get("baseline") or {"peer_note": "synthetic"}),
        "kb_hits": list(vig.get("kb_hits") or []),
        "allowed_evidence": allowed,
        "missing_evidence": list(vig.get("missing_evidence") or []),
        "watch_hits": list(vig.get("watch_hits") or []),
    }


def _predict_one(case: dict) -> dict:
    """走产品 Judge 契约：judge_v2 + normalize → verify → guardrails。

    直接调 chat 以保留 raw_text；判定逻辑与 enrich_judge 后处理一致，不改护栏。
    """
    inputs = _case_to_judge_inputs(case)
    allowed_set = set(inputs["allowed_evidence"])
    context = {
        "alert_trigger": {
            "type": inputs["alert"].get("alert_type"),
            "source": inputs["alert"].get("upstream"),
            "note": "仅为待复核线索，不直接决定 disposition",
        },
        "customer": {
            key: inputs["customer"].get(key)
            for key in ("id", "name", "kind", "industry", "opened_at", "kyc_level", "summary")
        },
        "findings": inputs["findings"],
        "transactions": inputs["transactions"][:30],
        "baseline": inputs["baseline"],
        "knowledge": [
            {"id": h.get("id"), "kind": h.get("kind"), "title": h.get("title"), "snippet": h.get("snippet")}
            for h in inputs["kb_hits"][:8]
        ],
        "allowed_evidence_ids": list(inputs["allowed_evidence"])[:120],
        "missing_evidence": inputs["missing_evidence"],
        "repair_issues": [],
        "output_limits": {
            "supporting_evidence_ids": 10,
            "contradicting_evidence_ids": 10,
            "rationale": 5,
            "evidence_ids_per_rationale": 6,
            "missing_evidence": 5,
            "next_actions": 5,
        },
        # 候选证据正文（产品路径里由工具结果提供；此处显式给出以避免空编号）
        "evidence_bundle": [
            {"id": e["id"], "text": e.get("text") or ""} for e in (case.get("vignette") or {}).get("candidate_evidence") or []
        ],
        "case_summary": case.get("vignette", {}).get("summary") or "",
    }
    raw_text = ""
    usage: dict = {}
    parse_ok = False
    verify: dict = {}
    guardrails: dict = {}
    pred = None
    support_ids: list[str] = []
    contra_ids: list[str] = []
    error = ""
    try:
        raw_text, usage = chat(
            [
                {"role": "system", "content": PROMPTS["judge_v2"]},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=JUDGE_MAX_TOKENS,
        )
        raw = _parse_model_json(raw_text, usage, role="Judge")
        decision = normalize_judge(raw, known_ids=allowed_set)
        parse_ok = True
        verify = verify_judge(decision, allowed_evidence=allowed_set)
        guardrails = apply_guardrails(decision, watch_hits=inputs["watch_hits"], fact_issues=None)
        pred = guardrails["final_conclusion"]
        support_ids = [x for x in (decision.get("supporting_evidence_ids") or []) if x in allowed_set]
        contra_ids = [x for x in (decision.get("contradicting_evidence_ids") or []) if x in allowed_set]
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:400]

    return {
        "case_id": case["case_id"],
        "tag": case.get("tag") or "",
        "gold": case["gold"],
        "pred": pred,
        "parse_ok": parse_ok,
        "verify_passed": bool(verify.get("passed")) if verify else False,
        "verify_issues": verify.get("issues") if verify else [],
        "guardrails_overridden": bool(guardrails.get("overridden")) if guardrails else False,
        "gold_support_ids": list(case.get("gold_support_ids") or case.get("gold_evidence_ids") or []),
        "gold_contradict_ids": list(case.get("gold_contradict_ids") or []),
        "pred_support_ids": support_ids,
        "pred_contradict_ids": contra_ids,
        "annotation_reason": case.get("annotation_reason") or "",
        "raw_text": (raw_text or "")[:4000],
        "usage": usage,
        "finish_reason": (usage or {}).get("finish_reason"),
        "completion_tokens": (usage or {}).get("completion_tokens"),
        "error": error,
    }


def evaluate_independent(*, limit: int | None = None, sleep_s: float = 0.0) -> dict:
    os.environ.pop("HUICHA_LLM_STUB", None)
    require_api_key()
    payload = load_split("independent_set.json")
    cases = list(payload.get("cases") or [])
    if limit is not None:
        cases = cases[: max(0, limit)]
    if not cases:
        raise RuntimeError("independent_set.json 为空，请先运行 build_independent_set.py")

    baselines = offline_baselines(cases)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{ts}.jsonl"

    rows: list[dict] = []
    call_errors = 0
    parse_failures = 0
    with run_path.open("w", encoding="utf-8") as fh:
        for i, case in enumerate(cases, start=1):
            row = _predict_one(case)
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
    support_ev = evidence_prf(
        [r["pred_support_ids"] for r in scored],
        [r["gold_support_ids"] for r in scored],
    )
    contra_ev = evidence_prf(
        [r["pred_contradict_ids"] for r in scored],
        [r["gold_contradict_ids"] for r in scored],
    )
    return {
        "label": "独立集 / 真实模型 / 产品 Judge 流水线",
        "protocol": "enrich_judge → normalize_judge → verify_judge → apply_guardrails",
        "prompt": "judge_v2",
        "split": "independent",
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
        "run_log": str(run_path.as_posix()),
        "baselines": baselines,
        "classification": clf,
        "by_tag": per_tag_report(rows),
        "evidence_support": support_ev,
        "evidence_contradict": contra_ev,
        "evidence_precision": support_ev.get("evidence_precision"),
        "evidence_recall": support_ev.get("evidence_recall"),
        "confusion_matrix": clf.get("confusion_matrix"),
        "macro_f1": clf.get("macro_f1"),
        "honesty": (
            "不是生产准确率；须人工签发。"
            "本协议已去除标签泄漏并走产品 Judge 契约；仍为合成 vignette。"
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
        "protocol": "product judge_v2 pipeline",
    }


def render_md_section(result: dict) -> list[str]:
    cm = (result.get("confusion_matrix") or {}).get("matrix") or {}
    labels = (result.get("confusion_matrix") or {}).get("labels") or list(LABELS)
    base = result.get("baselines") or {}
    lines = [
        "## 独立集 / 真实模型（v2 协议）",
        "",
        f"- 协议：`{result.get('protocol')}` · prompt=`{result.get('prompt')}`",
        f"- 标注集：`independent_set.json`（n={result['n']}，n_unique={result.get('n_unique_dataset')}，source={result.get('source')}）",
        f"- 模型：`{result.get('model')}`（真实调用）",
        f"- 计分条数：{result.get('n_scored')}（parse_failures={result.get('parse_failures')}，call_errors={result.get('call_errors')}）",
        f"- verify 通过率：{result.get('verify_pass_rate')}",
        f"- Macro-F1：**{result.get('macro_f1')}**",
        f"- Evidence 支持侧 P/R：**{result.get('evidence_precision')} / {result.get('evidence_recall')}**",
        f"- Evidence 反证侧 P/R：**{(result.get('evidence_contradict') or {}).get('evidence_precision')} / {(result.get('evidence_contradict') or {}).get('evidence_recall')}**",
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
    lines.extend(["", "### 按 tag 分组 Macro-F1", ""])
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


def update_results_md(result: dict) -> None:
    md_path = Path(__file__).parent / "RESULTS.md"
    text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    marker = "## 独立集 / 真实模型"
    stub_tail = (
        "## 能力指标占位（规则同源 stub）\n"
        "- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。\n"
        "- 上节为独立 vignette × 产品 Judge 的实验数字，禁止与 stub 机制验证混写成产品准确率。\n"
    )
    section = "\n".join(render_md_section(result))
    if marker in text:
        head, _, _rest = text.partition(marker)
        base = head.rstrip() + "\n\n"
    elif "## 5. 能力指标" in text:
        base = text.split("## 5. 能力指标")[0].rstrip() + "\n\n"
    else:
        base = text.rstrip() + "\n\n"
    md_path.write_text(base + section + "\n" + stub_tail, encoding="utf-8")


def update_results_json(result: dict) -> None:
    path = Path(__file__).parent / "RESULTS.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    # 降级旧结果
    if "independent_real_model" in data and "independent_real_model_v1_deprecated" not in data:
        old = data["independent_real_model"]
        old["deprecated"] = True
        old["deprecation_reason"] = (
            "v1：n_unique≈10、标签泄漏、自写 SYSTEM 贴合测试集、未走产品 Judge；"
            "仅作流水线打通记录，不得解释为模型能力。"
        )
        data["independent_real_model_v1_deprecated"] = old
    keep_keys = [
        "label",
        "protocol",
        "prompt",
        "split",
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
        "evidence_support",
        "evidence_contradict",
        "confusion_matrix",
        "baselines",
        "by_tag",
        "run_log",
        "honesty",
        "caveat",
        "legacy_note",
        "classification",
    ]
    data["independent_real_model"] = {k: result[k] for k in keep_keys if k in result}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="独立集上真实调用产品 Judge")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--baselines-only", action="store_true", help="只算离线基线，不调模型")
    args = parser.parse_args()
    if args.baselines_only:
        payload = load_split("independent_set.json")
        out = {
            "n": len(payload.get("cases") or []),
            "n_unique": payload.get("n_unique"),
            "baselines": offline_baselines(payload.get("cases") or []),
            "source": payload.get("source"),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    if not args.real:
        out = framework_status()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    result = evaluate_independent(limit=args.limit)
    update_results_json(result)
    update_results_md(result)
    printable = {k: v for k, v in result.items() if k != "by_tag"}
    printable["by_tag_n"] = len(result.get("by_tag") or {})
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
