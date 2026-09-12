"""Benchmark：独立合成标注集 + 真实百炼模型（须 DASHSCOPE_API_KEY）。

口径：输出混淆矩阵 / Macro-F1 / Evidence P&R，用于实验对照；
**不是**生产调查准确率，结论须人工签发。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.llm import _extract_json_object, chat, llm_model, require_api_key  # noqa: E402
from app.metrics_lib import LABELS, classification_report, evidence_prf  # noqa: E402

BENCH_DIR = Path(__file__).parent / "benchmark"
SYSTEM = """你是反洗钱调查建议助手。根据 vignette、signals 与候选证据，输出唯一 JSON 对象：
{"disposition":"exclude|observe|suggest_report","supporting_evidence_ids":["..."],"confidence":0.0}
判别口径（实验用，非终局报送）：
1) 若薪酬批次/保单赔付/财政补贴/监管放款等合理解释充分，且干扰线索不足以推翻，倾向 exclude；
2) 材料不完整或过桥用途不清，倾向 observe；
3) ATM 连环取现回流、循环开票闭环、现金对接虚拟资产、层叠空壳借款等异常节奏，倾向 suggest_report；
4) supporting_evidence_ids 只能从 candidate_evidence.id 选择，优先选与结论直接相关的编号；
5) 这不是生产准确率评估样本的终局结论；须人工签发后才是处置。
只输出 JSON，不要解释。"""


def load_split(name: str) -> dict:
    return json.loads((BENCH_DIR / name).read_text(encoding="utf-8"))


def _predict_one(case: dict) -> dict:
    vignette = case["vignette"]
    allowed = [e["id"] for e in vignette.get("candidate_evidence") or []]
    user = {
        "case_id": case["case_id"],
        "alert_type": vignette.get("alert_type"),
        "industry": vignette.get("industry"),
        "summary": vignette.get("summary"),
        "signals": vignette.get("signals"),
        "candidate_evidence": vignette.get("candidate_evidence"),
        "allowed_evidence_ids": allowed,
    }
    text, usage = chat(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=220,
    )
    data = _extract_json_object(text)
    disposition = str(data.get("disposition") or "").strip()
    if disposition not in LABELS:
        disposition = "observe"
    raw_ids = data.get("supporting_evidence_ids") or []
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    pred_ids = [str(x).strip() for x in raw_ids if str(x).strip() in set(allowed)]
    return {
        "case_id": case["case_id"],
        "gold": case["gold"],
        "pred": disposition,
        "gold_evidence_ids": list(case.get("gold_evidence_ids") or []),
        "pred_evidence_ids": pred_ids,
        "annotation_reason": case.get("annotation_reason") or "",
        "usage": usage,
    }


def evaluate_independent(*, limit: int | None = None, sleep_s: float = 0.05) -> dict:
    """独立标注集 + 真实模型。禁止在 stub/无密钥环境下宣称已评估。"""
    # 强制真实调用：关掉 stub 开关。
    os.environ.pop("HUICHA_LLM_STUB", None)
    require_api_key()
    payload = load_split("independent_set.json")
    cases = list(payload.get("cases") or [])
    if limit is not None:
        cases = cases[: max(0, limit)]
    if len(cases) < 1:
        raise RuntimeError("independent_set.json 为空，请先运行 build_independent_set.py")

    rows = []
    errors = 0
    for i, case in enumerate(cases, start=1):
        try:
            rows.append(_predict_one(case))
        except Exception as exc:  # noqa: BLE001 — 实验脚本需逐条容错
            errors += 1
            rows.append(
                {
                    "case_id": case["case_id"],
                    "gold": case["gold"],
                    "pred": "observe",
                    "gold_evidence_ids": list(case.get("gold_evidence_ids") or []),
                    "pred_evidence_ids": [],
                    "annotation_reason": case.get("annotation_reason") or "",
                    "error": str(exc)[:240],
                }
            )
        if i % 20 == 0:
            print(f"progress {i}/{len(cases)} errors={errors}", flush=True)
        if sleep_s:
            time.sleep(sleep_s)

    y_true = [r["gold"] for r in rows]
    y_pred = [r["pred"] for r in rows]
    clf = classification_report(y_true, y_pred)
    ev = evidence_prf(
        [r["pred_evidence_ids"] for r in rows],
        [r["gold_evidence_ids"] for r in rows],
    )
    return {
        "label": "独立集 / 真实模型",
        "split": "independent",
        "model": llm_model(),
        "n": len(rows),
        "errors": errors,
        "source": payload.get("source"),
        "caveat": payload.get("caveat"),
        "classification": clf,
        "evidence": ev,
        "confusion_matrix": clf.get("confusion_matrix"),
        "macro_f1": clf.get("macro_f1"),
        "evidence_precision": ev.get("evidence_precision"),
        "evidence_recall": ev.get("evidence_recall"),
        "honesty": "不是生产准确率；须人工签发后才是处置。",
        "sample": rows[:5],
    }


def framework_status() -> dict:
    golden = load_split("golden_set.json")
    test = load_split("test_set.json")
    independent = load_split("independent_set.json")
    return {
        "golden_n": len(golden.get("cases") or []),
        "test_n": len(test.get("cases") or []),
        "independent_n": len(independent.get("cases") or []),
        "note": golden.get("caveat"),
        "test_status": test.get("status"),
        "independent_caveat": independent.get("caveat"),
        "hint": "真实评估请运行: python experiments/benchmark.py --real",
    }


def render_md_section(result: dict) -> list[str]:
    cm = (result.get("confusion_matrix") or {}).get("matrix") or {}
    labels = (result.get("confusion_matrix") or {}).get("labels") or list(LABELS)
    lines = [
        "## 独立集 / 真实模型",
        "",
        f"- 标注集：`independent_set.json`（n={result['n']}，source={result.get('source')}）",
        f"- 模型：`{result.get('model')}`（真实百炼调用，非 stub）",
        f"- Macro-F1：**{result.get('macro_f1')}**",
        f"- Evidence P：**{result.get('evidence_precision')}** / R：**{result.get('evidence_recall')}**",
        f"- 调用失败条数：{result.get('errors')}",
        f"- 口径：{result.get('honesty')}",
        "",
        "### 混淆矩阵（行=gold，列=pred）",
        "",
        "| gold \\ pred | " + " | ".join(labels) + " |",
        "| --- | " + " | ".join(["---"] * len(labels)) + " |",
    ]
    for a in labels:
        row = cm.get(a) or {}
        lines.append("| " + a + " | " + " | ".join(str(row.get(b, 0)) for b in labels) + " |")
    lines.extend(
        [
            "",
            f"- per_class：`{json.dumps(result.get('classification', {}).get('per_class') or {}, ensure_ascii=False)}`",
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
        "- 上节为独立 vignette 集上的真实模型实验数字，禁止与 stub 机制验证混写成产品准确率。\n"
    )
    section = "\n".join(render_md_section(result))
    if marker in text:
        # 替换旧独立集章节到文末 stub 说明之前
        head, _, rest = text.partition(marker)
        # 丢掉旧独立集段落：从 marker 起到文件结束，再重写
        # 保留 stub 主体（marker 之前）
        base = head.rstrip() + "\n\n"
    else:
        # 把「## 5. 能力指标」替换为分节结构
        if "## 5. 能力指标" in text:
            base = text.split("## 5. 能力指标")[0].rstrip() + "\n\n"
        else:
            base = text.rstrip() + "\n\n"
    md_path.write_text(base + section + "\n" + stub_tail, encoding="utf-8")


def update_results_json(result: dict) -> None:
    path = Path(__file__).parent / "RESULTS.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["independent_real_model"] = {
        k: result[k]
        for k in (
            "label",
            "split",
            "model",
            "n",
            "errors",
            "source",
            "macro_f1",
            "evidence_precision",
            "evidence_recall",
            "confusion_matrix",
            "honesty",
            "caveat",
        )
        if k in result
    }
    data["independent_real_model"]["classification"] = result.get("classification")
    data["independent_real_model"]["evidence"] = result.get("evidence")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="在独立集上真实调用百炼")
    parser.add_argument("--limit", type=int, default=None, help="仅评估前 N 条（调试）")
    args = parser.parse_args()
    if not args.real:
        out = framework_status()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out
    result = evaluate_independent(limit=args.limit)
    update_results_json(result)
    update_results_md(result)
    print(json.dumps({k: result[k] for k in result if k != "sample"}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
