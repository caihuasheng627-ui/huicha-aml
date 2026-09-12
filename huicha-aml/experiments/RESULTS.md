# 循证慧查 机制验证（stub，可复现）

生成命令：`py -m app.experiments`

**口径**：下列数字验证「证据 Judge + 规则对照 + 硬护栏 + 回查」流水线能跑通。
精标由生成模板写入，Judge 为确定性 stub，**不是**独立标注集上的调查准确率。

## 1. 事实回查（正则，不经大模型）
- 毒化样本 n=200，拦截率 **100.0%**
- 干净阈值/概数误报率 **0.0%**（n=200）

## 2. AI Judge 与规则对照（非加权）
- 模板精标 n=87
- Judge 与规则对照分歧率 **40.2%**
- Judge 与模板标签重合 **100.0%**；规则对照重合 **59.8%**
- 重合率由合成模板与确定性 stub 构造，只用于检查流程，不是准确率。

## 3. 可审计机制
- 结构化引用契约通过率 **100.0%**
- 关键证据反事实覆盖率 **59.8%**
- 已执行反事实中结论变化率 **34.6%**（仅为机制指标）

## 4. 幻觉演示账号拦截：通过

说明：gold_label 仍由生成模板写入；Judge 为确定性 stub，不是真实百炼。这些数字只验证规则不再决定最终建议、引用契约与反事实流程可运行，不代表调查准确率。

## 独立集 / 真实模型（v2 协议）

- 协议：`enrich_judge → normalize_judge → verify_judge → apply_guardrails` · prompt=`judge_v2`
- 标注集：`independent_set.json`（n=5，n_unique=240，source=narrative_vignette_v2_combinatorial）
- 模型：`deepseek-v4-flash-0731`（真实调用）
- 计分条数：5（parse_failures=0，call_errors=0）
- verify 通过率：1.0
- Macro-F1：**0.1111**
- Evidence 支持侧 P/R：**0.5 / 0.8571**
- Evidence 反证侧 P/R：**0.0 / 0.0**
- 基线 Macro-F1：always_report=0.0 · keyword=0.5556
- 原始输出：`C:/Users/蔡华升/Desktop/新建文件夹/icbc/huicha-aml/experiments/benchmark/runs/20260912T132153Z.jsonl`
- 口径：不是生产准确率；须人工签发。本协议已去除标签泄漏并走产品 Judge 契约；仍为合成 vignette。
- 旧版说明：v1 结果（Macro-F1≈0.69）因 n_unique≈10、标签泄漏、自写 prompt 已降级，不得与本协议数字混比。

### 混淆矩阵（行=gold，列=pred；仅 parse 成功样本）

| gold \ pred | exclude | observe | suggest_report |
| --- | --- | --- | --- |
| exclude | 0 | 4 | 0 |
| observe | 0 | 1 | 0 |
| suggest_report | 0 | 0 | 0 |

### 按 tag 分组 Macro-F1

- `escrow_release` (gold=exclude, n=1): macro_f1=0.0, acc=0.0
- `gov_subsidy` (gold=exclude, n=1): macro_f1=0.0, acc=0.0
- `inheritance_partial` (gold=observe, n=1): macro_f1=0.3333, acc=1.0
- `insurance_claim` (gold=exclude, n=1): macro_f1=0.0, acc=0.0
- `payroll_batch` (gold=exclude, n=1): macro_f1=0.0, acc=0.0

- per_class：`{"exclude": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 4}, "observe": {"precision": 0.2, "recall": 1.0, "f1": 0.3333, "support": 1}, "suggest_report": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0}}`
- caveat：与 seed_extended 规则模板不同源的组合采样合成集；输入已去除家族名/关键干扰前缀/不透明证据 ID；annotation_reason 仅元数据，不进入模型上下文；不是人工专家标注；禁止写成生产准确率。

## 能力指标占位（规则同源 stub）
- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。
- 上节为独立 vignette × 产品 Judge 的实验数字，禁止与 stub 机制验证混写成产品准确率。
