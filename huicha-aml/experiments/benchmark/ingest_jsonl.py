"""把已有 jsonl 跑分重新汇总进 RESULTS（不调模型）。用于并行 --no-write 之后合并。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "experiments"))

from app.metrics_lib import LABELS, classification_report, evidence_prf  # noqa: E402
from benchmark import (  # noqa: E402
    BENCH_DIR,
    SET_FILES,
    _narrative_only,
    confidence_report,
    load_split,
    missing_evidence_report,
    offline_baselines,
    per_tag_report,
    update_results_json,
    update_results_md,
)


def ingest(jsonl: Path, set_name: str, prompt: str) -> dict:
    set_file = SET_FILES.get(set_name, set_name)
    if not str(set_file).endswith(".json"):
        set_file = f"{set_file}.json"
    payload = load_split(set_file)
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    scored = [r for r in rows if r.get("pred") in LABELS]
    y_true = [r["gold"] for r in scored]
    y_pred = [r["pred"] for r in scored]
    clf = classification_report(y_true, y_pred) if scored else classification_report([], [])
    support_ev = evidence_prf(
        [_narrative_only(r.get("pred_support_ids") or []) for r in scored],
        [r.get("gold_support_ids") or [] for r in scored],
    )
    contra_ev = evidence_prf(
        [_narrative_only(r.get("pred_contradict_ids") or []) for r in scored],
        [r.get("gold_contradict_ids") or [] for r in scored],
    )
    result = {
        "label": "独立集 / 真实模型 / 产品 Judge 流水线",
        "protocol": "enrich_judge(db=None) → normalize_judge → verify_judge → apply_guardrails",
        "prompt": prompt,
        "split": payload.get("split"),
        "variant": payload.get("variant") or set_name,
        "set_file": set_file,
        "model": next(((r.get("usage") or {}).get("model") for r in rows if (r.get("usage") or {}).get("model")), None),
        "n": len(rows),
        "n_unique_dataset": payload.get("n_unique"),
        "n_scored": len(scored),
        "parse_failures": sum(1 for r in rows if not r.get("parse_ok") or r.get("pred") not in LABELS),
        "call_errors": sum(1 for r in rows if r.get("error") and not r.get("parse_ok")),
        "verify_pass_rate": round(sum(1 for r in scored if r.get("verify_passed")) / len(scored), 4) if scored else 0.0,
        "source": payload.get("source"),
        "data_note": payload.get("data_note"),
        "caveat": payload.get("caveat"),
        "run_log": jsonl.relative_to(ROOT).as_posix() if jsonl.is_relative_to(ROOT) else str(jsonl),
        "baselines": offline_baselines(list(payload.get("cases") or [])),
        "classification": clf,
        "by_tag": per_tag_report(rows),
        "evidence_support": support_ev,
        "evidence_contradict": contra_ev,
        "evidence_precision": support_ev.get("evidence_precision"),
        "evidence_recall": support_ev.get("evidence_recall"),
        "evidence_scope": "仅叙事项 IX- 编号参与 P/R；TX-/KB- 引用不计入",
        "tx_cite_rate": round(
            sum(1 for r in scored if any(str(x).startswith("TX-") for x in (r.get("pred_support_ids") or []) + (r.get("pred_contradict_ids") or [])))
            / len(scored),
            4,
        )
        if scored
        else None,
        "confidence": confidence_report(scored),
        "missing_evidence": missing_evidence_report(scored),
        "confusion_matrix": clf.get("confusion_matrix"),
        "macro_f1": clf.get("macro_f1"),
        "observe_pred_rate": round(sum(1 for r in scored if r.get("pred") == "observe") / len(scored), 4) if scored else None,
        "honesty": "不是生产准确率；须人工签发。由 jsonl 回放汇总。",
        "legacy_note": "回放已有真实调用，不调模型。",
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl")
    parser.add_argument("--set", dest="set_name", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    result = ingest(Path(args.jsonl), args.set_name, args.prompt)
    if not args.no_write:
        ablation = update_results_json(result)
        update_results_md(result, ablation)
    print(json.dumps({k: result[k] for k in ("prompt", "source", "n_scored", "macro_f1", "observe_pred_rate", "run_log")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
