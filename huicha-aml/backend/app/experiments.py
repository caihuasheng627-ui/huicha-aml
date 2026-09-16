"""可复现机制实验：事实回查、Judge/规则分歧、引用契约与反事实。

用法：
  cd backend
  py -m app.experiments
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .agents import FAKE_ACCOUNT, run_investigation
from .database import Base
from .models import Alert
from .seed import seed_if_empty
from .tools import fact_check


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    seed_if_empty(db)
    return db


def experiment_fact_check(n: int = 200, seed: int = 42) -> dict:
    """向草稿注入不存在的账号/金额/编号，统计拦截率与干净文本误报。"""
    rng = random.Random(seed)
    facts = {
        "amounts": [188000.0, 49800.0, 300000.0],
        "tx_ids": ["TX-A-IN-01", "TX-B-IN-01", "TX-D-01"],
        "accounts": ["6222-A-8801", "6222-B-1908"],
        "dates": ["2026-09-10"],
        "names": ["华东百货批发有限公司", "C-A"],
        "kb_ids": ["KB-REG-01", "KB-TYP-01"],
    }
    clean_phrases = [
        "大额申报阈值为 5 万元,本案无接近阈值的拆分特征。",
        "月度流入约 200 万元量级。",
        "依据 KB-REG-01，交易编号 TX-A-IN-01 已核对。",
        "客户华东百货批发有限公司账户 6222-A-8801 经营特征相符。",
    ]
    intercept = 0
    clean_false = 0
    for i in range(n):
        kind = i % 3
        if kind == 0:
            draft = f"另发现对手账户 6222-FAKE-{rng.randint(1000,9999)}。"
        elif kind == 1:
            draft = f"另转出 {rng.randint(60,99)}.{rng.randint(10,99)} 万元至陌生账户。"
        else:
            draft = f"关键虚构编号 TX-FAKE-{rng.randint(100,999)}。"
        issues = fact_check(draft, facts)
        if issues:
            intercept += 1
    for p in clean_phrases * (n // len(clean_phrases)):
        if fact_check(p, facts):
            clean_false += 1
    clean_n = len(clean_phrases) * (n // len(clean_phrases))
    return {
        "name": "事实回查拦截率",
        "n_poison": n,
        "intercept_rate": round(intercept / n, 4),
        "n_clean": clean_n,
        "clean_false_positive_rate": round(clean_false / max(clean_n, 1), 4),
        "note": "毒化草稿含虚构账号/金额/编号；干净句含阈值与概数措辞。",
    }


def experiment_ablation_and_consistency(db, monkey_chat=None) -> dict:
    """统计 AI Judge 与独立规则对照的分歧、引用契约和反事实覆盖。"""
    if monkey_chat:
        import app.llm as llm_mod

        llm_mod.chat = monkey_chat  # type: ignore

    alerts = db.query(Alert).filter(Alert.gold_label != "").all()
    rows = []
    judge_gold_match = 0
    rule_gold_match = 0
    judge_rule_disagree = 0
    citation_pass = 0
    counterfactual_run = 0
    counterfactual_faithful = 0
    for a in alerts:
        gold = a.gold_label
        r_on = run_investigation(db, a.id, use_challenger=True, inject_hallucination=False)
        rule = r_on["rule_baseline"]
        cf = r_on["counterfactual"]
        rows.append(
            {
                "id": a.id,
                "gold": gold,
                "judge": r_on["conclusion"],
                "rule_baseline": rule["conclusion"],
                "demo_tag": a.demo_tag,
                "citation_contract": r_on["judge_validation"]["passed"],
                "counterfactual_performed": cf["performed"],
                "counterfactual_faithful": cf["faithful"],
            }
        )
        if r_on["conclusion"] == gold:
            judge_gold_match += 1
        if rule["conclusion"] == gold:
            rule_gold_match += 1
        if r_on["conclusion"] != rule["conclusion"]:
            judge_rule_disagree += 1
        citation_pass += int(r_on["judge_validation"]["passed"])
        counterfactual_run += int(cf["performed"])
        counterfactual_faithful += int(cf["faithful"] is True)

    n = len(rows) or 1
    return {
        "name": "机制验证：证据 Judge vs 独立规则对照（固定 stub）",
        "n_labeled": len(rows),
        "judge_template_match_rate": round(judge_gold_match / n, 4),
        "rule_template_match_rate": round(rule_gold_match / n, 4),
        "judge_rule_disagreement_rate": round(judge_rule_disagree / n, 4),
        "citation_contract_pass_rate": round(citation_pass / n, 4),
        "counterfactual_coverage": round(counterfactual_run / n, 4),
        "counterfactual_change_rate": round(counterfactual_faithful / max(counterfactual_run, 1), 4),
        "sample": [r for r in rows if r["demo_tag"] in {"A", "B", "C", "F", "L"}][:10],
        "caveat": (
            "gold_label 仍由生成模板写入；Judge 为确定性 stub，不是真实百炼。"
            "这些数字只验证规则不再决定最终建议、引用契约与反事实流程可运行，不代表调查准确率。"
        ),
    }


def _stub_chat(messages, *, temperature=0.0, max_tokens=900, **_kwargs):
    from .llm import _offline_stub_chat

    return _offline_stub_chat(messages)


def run_all(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or Path(__file__).resolve().parents[1].parent / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    db = _session()
    import app.llm as llm_mod
    import os

    os.environ["DASHSCOPE_API_KEY"] = "sk-experiment-stub"
    llm_mod._ENV_LOADED = False
    llm_mod.chat = _stub_chat  # type: ignore

    fact = experiment_fact_check(200)
    abl = experiment_ablation_and_consistency(db)
    # 幻觉拦截抽检
    hall = run_investigation(db, "ALT-A-20260910", use_challenger=True, inject_hallucination=True)
    hall_ok = any(i["token"] == FAKE_ACCOUNT for i in hall["fact_issues"])

    results = {
        "fact_check": fact,
        "ablation_consistency": abl,
        "hallucination_demo_intercepted": hall_ok,
    }
    (out_dir / "RESULTS.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# 循证慧查 机制验证（stub，可复现）",
        "",
        "生成命令：`py -m app.experiments`",
        "",
        "**口径**：下列数字验证「证据 Judge + 规则对照 + 硬护栏 + 回查」流水线能跑通。",
        "精标由生成模板写入，Judge 为确定性 stub，**不是**独立标注集上的调查准确率。",
        "",
        "## 1. 事实回查（正则，不经大模型）",
        f"- 毒化样本 n={fact['n_poison']}，拦截率 **{fact['intercept_rate']:.1%}**",
        f"- 干净阈值/概数误报率 **{fact['clean_false_positive_rate']:.1%}**（n={fact['n_clean']}）",
        "",
        "## 2. AI Judge 与规则对照（非加权）",
        f"- 模板精标 n={abl['n_labeled']}",
        f"- Judge 与规则对照分歧率 **{abl['judge_rule_disagreement_rate']:.1%}**",
        f"- Judge 与模板标签重合 **{abl['judge_template_match_rate']:.1%}**；规则对照重合 **{abl['rule_template_match_rate']:.1%}**",
        "- 重合率由合成模板与确定性 stub 构造，只用于检查流程，不是准确率。",
        "",
        "## 3. 可审计机制",
        f"- 结构化引用契约通过率 **{abl['citation_contract_pass_rate']:.1%}**",
        f"- 关键证据反事实覆盖率 **{abl['counterfactual_coverage']:.1%}**",
        f"- 已执行反事实中结论变化率 **{abl['counterfactual_change_rate']:.1%}**（仅为机制指标）",
        "",
        f"## 4. 幻觉演示账号拦截：{'通过' if hall_ok else '失败'}",
        "",
        "## 5. 能力指标（独立标注集）",
        "- Accuracy / Precision / Recall / F1 / Macro-F1 / FPR / Evidence P&R：**Not evaluated yet**",
        "- 请运行 `python experiments/benchmark.py` 查看框架状态，不要把本节写成产品准确率。",
        "",
        f"说明：{abl['caveat']}",
    ]
    (out_dir / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    db.close()
    return results


if __name__ == "__main__":
    r = run_all()
    print(json.dumps(r, ensure_ascii=False, indent=2))
