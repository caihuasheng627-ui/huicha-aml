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

## B. 独立集 / 真实模型（v2 协议 · 全量）

**诚实声明**：合成 vignette，非专家标注，**不是生产准确率**；须人工签发。  
v1（Macro-F1≈0.69）已因泄漏假集合降级，**不得与本节混比**。

| 项 | 值 |
| --- | --- |
| 协议 | `judge_v2` → normalize → verify → guardrails |
| 数据集 | `independent_set.json`（n=240，**n_unique=240**） |
| 模型 | `deepseek-v4-flash-0731`（真实百炼） |
| parse / call 失败 | **0 / 0** |
| verify 通过率 | **1.0** |
| Macro-F1 | **0.1686** |
| Accuracy | 0.2292 |
| Evidence 支持 P/R | 0.3736 / 0.8397 |
| Evidence 反证 P/R | 0.0 / 0.0 |
| 基线 Macro-F1 | always_report **0.2082** · keyword **0.867** |
| 原始日志 | `experiments/benchmark/runs/20260912T132445Z.jsonl` |

### 混淆矩阵（行=gold，列=pred）

| gold \ pred | exclude | observe | suggest_report |
| --- | ---: | ---: | ---: |
| exclude | 0 | 87 | 0 |
| observe | 0 | 44 | 0 |
| suggest_report | 0 | 98 | 11 |

### 分档指标

| 标签 | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| exclude | 0.0000 | 0.0000 | 0.0000 | 87 |
| observe | 0.1921 | 1.0000 | 0.3223 | 44 |
| suggest_report | 1.0000 | 0.1009 | 0.1833 | 109 |

### 按 tag（摘要）

- 两档 observe 族（`inheritance_partial` / `purpose_docs_gap`）：acc=1.0（全判观察）
- 四档 exclude 族：acc=0（全部压成观察）
- 上报族：仅 `crypto_onramp` 等少量命中；多数（如 `atm_smurf`/`nested_shell_loan`）几乎全成观察

### 读数要点（给评审）

1. **流水线可信**：全量可解析、契约全过——实验协议本身成立。  
2. **判别偏置**：模型几乎「默认 observe」（229/240），排除档召回 0，上报档召回仅约 10%。  
3. **相对基线**：Macro-F1 **低于** always_report（0.21），**远低于** keyword（0.87）→ 当前产品 Judge 在本合成集上未学到可操作的三档边界，主要在做保守观望。  
4. **安全面**：FPR（以上报为正类）=0，未见「该排除却直接上报」。  
5. **下一步**应改观察/排除/上报的可操作判据与少样本，而不是继续刷泄漏集分数。

完整叙述见 [`REAL_MODEL_REPORT.md`](./REAL_MODEL_REPORT.md)。

---

## C. 规则同源 stub 占位

- `golden_set` / `test_set` 仍为框架槽位；勿与 B 节混写为产品准确率。

## 独立集 / 真实模型（v3 协议 · prompt=judge_v2）

- 协议：`enrich_judge(db=None) → normalize_judge → verify_judge → apply_guardrails` · prompt=`judge_v2`
- 标注集：`independent_set.json`（n=240，n_unique=240，source=narrative_vignette_v3_rules_layer）
- 模型：`deepseek-v4-flash-0731`（真实调用）
- 计分条数：237（parse_failures=3，call_errors=3）
- verify 通过率：1.0
- Macro-F1：**0.3867**
- Evidence 支持侧 P/R：**0.7023 / 0.6113**（仅叙事项 IX- 编号参与 P/R；TX-/KB- 引用不计入）
- Evidence 反证侧 P/R：**0.087 / 0.3077**
- 引用过 TX- 编号的样本比例：0.9958
- 基线 Macro-F1：always_report=0.2069 · keyword=0.8031
- 原始输出：`/workspace/huicha-aml/experiments/benchmark/runs/20260912T144147Z_judge_v2.jsonl`
- 口径：不是生产准确率；须人工签发。本协议已去除标签泄漏并走产品 Judge 契约（enrich_judge 直调）；仍为合成 vignette。
- 旧版说明：v1 结果（Macro-F1≈0.69）因 n_unique≈10、标签泄漏、自写 prompt 已降级，不得与本协议数字混比。

### 混淆矩阵（行=gold，列=pred；仅 parse 成功样本）

| gold \ pred | exclude | observe | suggest_report |
| --- | --- | --- | --- |
| exclude | 0 | 88 | 0 |
| observe | 0 | 43 | 1 |
| suggest_report | 0 | 40 | 65 |

### confidence 分布

| 区间 | [0.0,0.2) | [0.2,0.4) | [0.4,0.6) | [0.6,0.8) | [0.8,1.0] |
| --- | --- | --- | --- | --- | --- |
| 条数 | 0 | 0 | 71 | 146 | 20 |

- 去重取值数=9 · mean=0.6741 · stdev=0.0949 · min/max=0.55/0.82
- 按 gold 均值：`{"exclude": 0.7036, "observe": 0.5539, "suggest_report": 0.6998}` · 按 pred 均值：`{"observe": 0.6367, "suggest_report": 0.7712}`
- 最常见取值：`{"0.55": 71, "0.72": 47, "0.75": 35, "0.65": 27, "0.78": 23, "0.82": 20}`

### missing_evidence 契约

- observe 预测中带非空 missing_evidence 的比例：**1.0**
- 按 pred：`{"exclude": {"n": 0, "with_missing_n": 0, "with_missing_ratio": null, "avg_missing_len": null}, "observe": {"n": 171, "with_missing_n": 171, "with_missing_ratio": 1.0, "avg_missing_len": 2.959}, "suggest_report": {"n": 66, "with_missing_n": 66, "with_missing_ratio": 1.0, "avg_missing_len": 3.0}}`
- 被 sanitize 掉的编号样条目数：0

### 按 tag 分组 Macro-F1

- `atm_smurf` (gold=suggest_report, n=22): macro_f1=0.2906, acc=0.7727
- `crowdfund_layering` (gold=suggest_report, n=20): macro_f1=0.2745, acc=0.7
- `crypto_onramp` (gold=suggest_report, n=22): macro_f1=0.3333, acc=1.0
- `escrow_release` (gold=exclude, n=22): macro_f1=0.0, acc=0.0
- `gov_subsidy` (gold=exclude, n=22): macro_f1=0.0, acc=0.0
- `inheritance_partial` (gold=observe, n=22): macro_f1=0.3256, acc=0.9545
- `insurance_claim` (gold=exclude, n=22): macro_f1=0.0, acc=0.0
- `invoice_circular` (gold=suggest_report, n=22): macro_f1=0.1609, acc=0.3182
- `nested_shell_loan` (gold=suggest_report, n=19): macro_f1=0.1389, acc=0.2632
- `payroll_batch` (gold=exclude, n=22): macro_f1=0.0, acc=0.0
- `purpose_docs_gap` (gold=observe, n=22): macro_f1=0.3333, acc=1.0

- per_class：`{"exclude": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 88}, "observe": {"precision": 0.2515, "recall": 0.9773, "f1": 0.4, "support": 44}, "suggest_report": {"precision": 0.9848, "recall": 0.619, "f1": 0.7602, "support": 105}}`
- caveat：与 seed_extended 规则模板不同源的组合采样合成集；流水按叙事族真实结构生成并经产品 analyst_rules.analyze() 产出规则层 findings；叙事项带 support/counter/context 极性；不向 Judge 传 missing_evidence；输入已去除家族名/关键干扰前缀/合成占位字样；annotation_reason 仅元数据；不是人工专家标注；禁止写成生产准确率。

## 能力指标占位（规则同源 stub）
- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。
- 上节为独立 vignette × 产品 Judge 的实验数字，禁止与 stub 机制验证混写成产品准确率。
