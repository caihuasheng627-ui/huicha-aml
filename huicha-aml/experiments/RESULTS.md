# 循证慧查 机制验证与能力实验

## A. Stub 机制验证（可复现，非准确率）

生成命令：`py -m app.experiments`

**口径**：验证「证据 Judge + 规则对照 + 硬护栏 + 回查」能跑通。精标与规则同源，Judge 为 stub。

### 1. 事实回查
- 毒化样本 n=200，拦截率 **100.0%**
- 干净阈值/概数误报率 **0.0%**（n=200）

### 2. AI Judge 与规则对照（stub）
- 模板精标 n=87；Judge↔规则分歧 **40.2%**
- 仅用于检查流程，不是准确率

### 3. 可审计机制
- 引用契约通过率 **100.0%**；关键证据反事实覆盖率 **59.8%**

### 4. 幻觉演示账号拦截：通过

---

## B. 独立集 v2 协议（历史结果，已被 v3 集替代，不得与 v3 混比）

v2 集（`narrative_vignette_v2_combinatorial`，2026-09-12 13:24 跑）在复审中确认存在两处实验有效性问题，因此其数字只保留为历史记录：

| 项 | 值 | 复审结论 |
| --- | --- | --- |
| Macro-F1 / Accuracy | 0.1686 / 0.2292 | 低于 always_report 基线（0.2082） |
| 混淆矩阵 | exclude 87→observe 87；suggest_report 109→observe 98 | 三档塌缩为「观察」 |
| 泄漏 1 | 只有 observe 族携带 `missing_evidence` 输入 | 标签可由输入字段直接推出 |
| 泄漏 2 / 缺口 | findings 全部 `polarity=context`、无规则层；`peer_note`/客户名/备注含「合成/占位」字样；证据编号 `EV-` 被产品 `enrich_judge` 过滤 | Judge 看到的输入与产品路径不同构 |

v3 集（下节）逐项修复了上述问题；v3 集上 `judge_v2` 的重跑结果见消融表，用作 prompt 改动的对照组。
完整叙述见 [`REAL_MODEL_REPORT.md`](./REAL_MODEL_REPORT.md)。

---

## 独立集 / 真实模型（v3 协议 · prompt=judge_v4）

- 协议：`enrich_judge(db=None) → normalize_judge → verify_judge → apply_guardrails` · prompt=`judge_v4`
- 标注集：`independent_set.json`（n=220，n_unique=220，source=narrative_vignette_blind_holdout）
- 模型：`deepseek-v4-flash-0731`（真实调用）
- 计分条数：215（parse_failures=5，call_errors=5）
- verify 通过率：1.0
- Macro-F1：**0.994**
- Evidence 支持侧 P/R：**0.777 / 0.9672**（仅叙事项 IX- 编号参与 P/R；TX-/KB- 引用不计入）
- Evidence 反证侧 P/R：**0.4205 / 0.3895**
- 引用过 TX- 编号的样本比例：0.9953
- 基线 Macro-F1：always_report=0.2083 · keyword=0.1096
- 原始输出：`experiments/benchmark/runs/20260913T003147Z_blind_judge_v4.jsonl`
- 口径：不是生产准确率；须人工签发。由 jsonl 回放汇总。
- 旧版说明：回放已有真实调用，不调模型。

### 混淆矩阵（行=gold，列=pred；仅 parse 成功样本）

| gold \ pred | exclude | observe | suggest_report |
| --- | --- | --- | --- |
| exclude | 80 | 0 | 0 |
| observe | 0 | 39 | 0 |
| suggest_report | 0 | 1 | 95 |

### confidence 分布

| 区间 | [0.0,0.2) | [0.2,0.4) | [0.4,0.6) | [0.6,0.8) | [0.8,1.0] |
| --- | --- | --- | --- | --- | --- |
| 条数 | 0 | 0 | 40 | 49 | 126 |

- 去重取值数=4 · mean=0.7391 · stdev=0.1467 · min/max=0.45/0.85
- 按 gold 均值：`{"exclude": 0.8466, "observe": 0.45, "suggest_report": 0.767}` · 按 pred 均值：`{"exclude": 0.8466, "observe": 0.45, "suggest_report": 0.7703}`
- 最常见取值：`{"0.85": 77, "0.82": 49, "0.72": 49, "0.45": 40}`

### missing_evidence 契约

- observe 预测中带非空 missing_evidence 的比例：**1.0**
- 按 pred：`{"exclude": {"n": 80, "with_missing_n": 0, "with_missing_ratio": 0.0, "avg_missing_len": 0.0}, "observe": {"n": 40, "with_missing_n": 40, "with_missing_ratio": 1.0, "avg_missing_len": 2.95}, "suggest_report": {"n": 95, "with_missing_n": 89, "with_missing_ratio": 0.9368, "avg_missing_len": 2.747}}`
- 被 sanitize 掉的编号样条目数：0

### 按 tag 分组 Macro-F1

- `court_award` (gold=exclude, n=20): macro_f1=0.3333, acc=1.0
- `demolition_comp` (gold=exclude, n=20): macro_f1=0.3333, acc=1.0
- `docs_pending` (gold=observe, n=19): macro_f1=0.3333, acc=1.0
- `dual_pledge` (gold=suggest_report, n=20): macro_f1=0.3333, acc=1.0
- `equity_transfer` (gold=exclude, n=20): macro_f1=0.3333, acc=1.0
- `first_large` (gold=observe, n=20): macro_f1=0.3333, acc=1.0
- `fx_split` (gold=suggest_report, n=19): macro_f1=0.3243, acc=0.9474
- `seasonal_stock` (gold=exclude, n=20): macro_f1=0.3333, acc=1.0
- `shell_payroll` (gold=suggest_report, n=19): macro_f1=0.3333, acc=1.0
- `staff_pass` (gold=suggest_report, n=20): macro_f1=0.3333, acc=1.0
- `wager_proxy` (gold=suggest_report, n=18): macro_f1=0.3333, acc=1.0

- per_class：`{"exclude": {"precision": 1.0, "recall": 1.0, "f1": 1.0, "support": 80}, "observe": {"precision": 0.975, "recall": 1.0, "f1": 0.9873, "support": 39}, "suggest_report": {"precision": 1.0, "recall": 0.9896, "f1": 0.9948, "support": 96}}`
- caveat：与 seed_extended 规则模板不同源的组合采样合成集；流水按叙事族真实结构生成并经产品 analyst_rules.analyze() 产出规则层 findings；不向 Judge 传 missing_evidence；输入已去除家族名/关键干扰前缀/合成占位字样；annotation_reason 仅元数据；不是人工专家标注；禁止写成生产准确率。叙事文本不含 judge_v3 判定标准中例举的任何类型学词；类型学形态在例举之外。规则层 finding 文本为产品输出，不受禁词约束。

## 消融：judge prompt 版本对比（同一独立集）

- 同一 independent_set.json、同一模型、同一后处理；唯一变量为 judge prompt 版本。

| 指标 | `judge_v2` | `judge_v3` | `judge_v4` |
| --- | --- | --- | --- |
| Macro-F1 | 0.3867 | 0.9662 | 0.9480 |
| Accuracy | 0.4557 | 0.9745 | 0.9609 |
| Evidence P（支持侧） | 0.7023 | 0.7644 | 0.7488 |
| Evidence R（支持侧） | 0.6113 | 0.8640 | 0.8699 |
| verify 通过率 | 1.0000 | 1.0000 | 1.0000 |
| parse_failures | 3 | 5 | 10 |
| confidence 去重取值数 | 9 | 7 | 6 |
| confidence 标准差 | 0.0949 | 0.1417 | 0.1422 |
| observe 带 missing 比例 | 1.0000 | 1.0000 | 1.0000 |
| exclude 召回 | 0.0000 | 1.0000 | 0.9886 |
| observe 召回 | 0.9773 | 0.8636 | 0.8372 |
| suggest_report 召回 | 0.6190 | 1.0000 | 0.9899 |
| observe 预测率 | — | — | 0.1652 |

- `judge_v2` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 0, "observe": 88, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 43, "suggest_report": 1}, "suggest_report": {"exclude": 0, "observe": 40, "suggest_report": 65}}` · 原始输出 `experiments/benchmark/runs/20260912T144147Z_judge_v2.jsonl`
- `judge_v3` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 88, "observe": 0, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 38, "suggest_report": 6}, "suggest_report": {"exclude": 0, "observe": 0, "suggest_report": 103}}` · 原始输出 `experiments/benchmark/runs/20260912T151253Z_judge_v3.jsonl`
- `judge_v4` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 87, "observe": 1, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 36, "suggest_report": 7}, "suggest_report": {"exclude": 0, "observe": 1, "suggest_report": 98}}` · 原始输出 `experiments/benchmark/runs/20260913T003147Z_v3_judge_v4.jsonl`

## 消融：judge prompt 版本对比（同一独立集）

- 同一 independent_set.json、同一模型、同一后处理；唯一变量为 judge prompt 版本。

| 指标 | `judge_v2` | `judge_v3` |
| --- | --- | --- |
| Macro-F1 | 0.3434 | 0.9656 |
| Accuracy | 0.4008 | 0.9744 |
| Evidence P（支持侧） | 0.6980 | 0.6606 |
| Evidence R（支持侧） | 0.7746 | 0.8343 |
| verify 通过率 | 1.0000 | 0.9957 |
| parse_failures | 3 | 6 |
| confidence 去重取值数 | 7 | 9 |
| confidence 标准差 | 0.0969 | 0.1415 |
| observe 带 missing 比例 | 1.0000 | 1.0000 |
| exclude 召回 | 0.0000 | 1.0000 |
| observe 召回 | 0.9767 | 0.8605 |
| suggest_report 召回 | 0.4953 | 1.0000 |
| observe 预测率 | 0.7722 | 0.1581 |

- `judge_v2` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 0, "observe": 87, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 42, "suggest_report": 1}, "suggest_report": {"exclude": 0, "observe": 54, "suggest_report": 53}}` · 原始输出 `experiments/benchmark/runs/20260912T173531Z_nopolarity_judge_v2.jsonl`
- `judge_v3` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 88, "observe": 0, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 37, "suggest_report": 6}, "suggest_report": {"exclude": 0, "observe": 0, "suggest_report": 103}}` · 原始输出 `experiments/benchmark/runs/20260912T183509Z_nopolarity_judge_v3.jsonl`

## 消融：judge prompt 版本对比（同一独立集）

- 同一 independent_set.json、同一模型、同一后处理；唯一变量为 judge prompt 版本。

| 指标 | `judge_v2` | `judge_v3` | `judge_v4` |
| --- | --- | --- | --- |
| Macro-F1 | 0.4259 | 0.9286 | 0.9940 |
| Accuracy | 0.5139 | 0.9493 | 0.9953 |
| Evidence P（支持侧） | 0.7362 | 0.7715 | 0.7770 |
| Evidence R（支持侧） | 0.7101 | 0.9290 | 0.9672 |
| verify 通过率 | 1.0000 | 1.0000 | 1.0000 |
| parse_failures | 4 | 3 | 5 |
| confidence 去重取值数 | 9 | 7 | 4 |
| confidence 标准差 | 0.1053 | 0.1338 | 0.1467 |
| observe 带 missing 比例 | 1.0000 | 1.0000 | 1.0000 |
| exclude 召回 | 0.0000 | 0.9875 | 1.0000 |
| observe 召回 | 1.0000 | 0.7436 | 1.0000 |
| suggest_report 召回 | 0.7320 | 1.0000 | 0.9896 |
| observe 预测率 | 0.6713 | 0.1382 | 0.1860 |

- `judge_v2` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 0, "observe": 79, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 40, "suggest_report": 0}, "suggest_report": {"exclude": 0, "observe": 26, "suggest_report": 71}}` · 原始输出 `experiments/benchmark/runs/20260912T165213Z_blind_judge_v2.jsonl`
- `judge_v3` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 79, "observe": 1, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 29, "suggest_report": 10}, "suggest_report": {"exclude": 0, "observe": 0, "suggest_report": 98}}` · 原始输出 `experiments/benchmark/runs/20260912T161440Z_blind_judge_v3.jsonl`
- `judge_v4` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 80, "observe": 0, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 39, "suggest_report": 0}, "suggest_report": {"exclude": 0, "observe": 1, "suggest_report": 95}}` · 原始输出 `experiments/benchmark/runs/20260913T003147Z_blind_judge_v4.jsonl`

## 消融：judge prompt 版本对比（同一独立集）

- 同一 independent_set.json、同一模型、同一后处理；唯一变量为 judge prompt 版本。

| 指标 | `judge_v2` | `judge_v3` |
| --- | --- | --- |
| Macro-F1 | 0.4027 | 0.9630 |
| Accuracy | 0.4679 | 0.9724 |
| Evidence P（支持侧） | 0.6969 | 0.7539 |
| Evidence R（支持侧） | 0.6637 | 1.0000 |
| verify 通过率 | 1.0000 | 1.0000 |
| parse_failures | 2 | 3 |
| confidence 去重取值数 | 9 | 8 |
| confidence 标准差 | 0.1011 | 0.1397 |
| observe 带 missing 比例 | 1.0000 | 1.0000 |
| exclude 召回 | 0.0256 | 1.0000 |
| observe 召回 | 1.0000 | 0.8718 |
| suggest_report 召回 | 0.6000 | 0.9898 |
| observe 预测率 | 0.7156 | 0.1613 |

- `judge_v2` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 2, "observe": 76, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 40, "suggest_report": 0}, "suggest_report": {"exclude": 0, "observe": 40, "suggest_report": 60}}` · 原始输出 `experiments/benchmark/runs/20260912T235835Z_blind_struct_judge_v2.jsonl`
- `judge_v3` 混淆矩阵（行=gold）：`{"exclude": {"exclude": 80, "observe": 0, "suggest_report": 0}, "observe": {"exclude": 0, "observe": 34, "suggest_report": 5}, "suggest_report": {"exclude": 0, "observe": 1, "suggest_report": 97}}` · 原始输出 `experiments/benchmark/runs/20260912T235835Z_blind_struct_judge_v3.jsonl`

## 有效性消融（主集 / 去极性 / 盲区 / 结构盲区）

- 跨数据集对比：v3 主集 / 去极性 / 盲区 / 结构盲区；按模型分槽，禁止跨模型混比。

### `narrative_vignette_blind_holdout`

| 指标 | `judge_v2` | `judge_v3` | `judge_v4` |
| --- | --- | --- | --- |
| Macro-F1 | 0.4259 | 0.9286 | 0.9940 |
| exclude 召回 | 0.0000 | 0.9875 | 1.0000 |
| suggest_report 召回 | 0.7320 | 1.0000 | 0.9896 |
| observe 预测率 | 0.6713 | 0.1382 | 0.1860 |

### `narrative_vignette_blind_struct`

| 指标 | `judge_v2` | `judge_v3` |
| --- | --- | --- |
| Macro-F1 | 0.4027 | 0.9630 |
| exclude 召回 | 0.0256 | 1.0000 |
| suggest_report 召回 | 0.6000 | 0.9898 |
| observe 预测率 | 0.7156 | 0.1613 |

### `narrative_vignette_blind_struct__deepseek-chat`

| 指标 | `judge_v3` | `judge_v4` |
| --- | --- | --- |
| Macro-F1 | 0.8776 | 0.8661 |
| exclude 召回 | 0.9625 | 0.8500 |
| suggest_report 召回 | 0.7900 | 0.8600 |
| observe 预测率 | 0.2909 | 0.3000 |

### `narrative_vignette_v3_rules_layer`

| 指标 | `judge_v2` | `judge_v3` | `judge_v4` |
| --- | --- | --- | --- |
| Macro-F1 | 0.3867 | 0.9662 | 0.9480 |
| exclude 召回 | 0.0000 | 1.0000 | 0.9886 |
| suggest_report 召回 | 0.6190 | 1.0000 | 0.9899 |
| observe 预测率 | — | — | 0.1652 |

### `narrative_vignette_v3_rules_layer_nopolarity`

| 指标 | `judge_v2` | `judge_v3` |
| --- | --- | --- |
| Macro-F1 | 0.3434 | 0.9656 |
| exclude 召回 | 0.0000 | 1.0000 |
| suggest_report 召回 | 0.4953 | 1.0000 |
| observe 预测率 | 0.7722 | 0.1581 |

## 能力指标占位（规则同源 stub）
- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。
- 上节为独立 vignette × 产品 Judge 的实验数字，禁止与 stub 机制验证混写成产品准确率。
