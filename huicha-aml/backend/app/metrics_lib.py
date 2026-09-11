"""分类指标。仅用于实验脚本，禁止把构造集数字写成产品准确率。"""

from __future__ import annotations

from collections import Counter


LABELS = ("exclude", "observe", "suggest_report")


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


def classification_report(y_true: list[str], y_pred: list[str]) -> dict:
    n = len(y_true)
    acc = sum(a == b for a, b in zip(y_true, y_pred)) / n if n else 0.0
    per: dict[str, dict] = {}
    f1s = []
    for lab in LABELS:
        tp = sum(a == lab and b == lab for a, b in zip(y_true, y_pred))
        fp = sum(a != lab and b == lab for a, b in zip(y_true, y_pred))
        fn = sum(a == lab and b != lab for a, b in zip(y_true, y_pred))
        p, r, f1 = _prf(tp, fp, fn)
        per[lab] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "support": tp + fn}
        f1s.append(f1)
    # 以 suggest_report 为正类的 FPR
    tn = sum(a != "suggest_report" and b != "suggest_report" for a, b in zip(y_true, y_pred))
    fp_pos = sum(a != "suggest_report" and b == "suggest_report" for a, b in zip(y_true, y_pred))
    fpr = fp_pos / (fp_pos + tn) if (fp_pos + tn) else 0.0
    return {
        "n": n,
        "accuracy": round(acc, 4),
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "false_positive_rate": round(fpr, 4),
        "per_class": per,
        "label_dist": dict(Counter(y_true)),
        "note": "对本输入列表有效；不是生产准确率。",
    }


def evidence_prf(predicted: list[list[str]], gold: list[list[str]]) -> dict:
    tp = fp = fn = 0
    for pred, g in zip(predicted, gold):
        ps, gs = set(pred), set(g)
        tp += len(ps & gs)
        fp += len(ps - gs)
        fn += len(gs - ps)
    p, r, f1 = _prf(tp, fp, fn)
    return {
        "evidence_precision": round(p, 4),
        "evidence_recall": round(r, 4),
        "evidence_f1": round(f1, 4),
        "note": "需要人工 gold evidence；当前仓库未提供独立标注。TODO",
    }
