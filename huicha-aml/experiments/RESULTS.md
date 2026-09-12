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

## 独立集 / 真实模型

- 标注集：`independent_set.json`（n=220，source=narrative_vignette_v1）
- 模型：`deepseek-v4-flash-0731`（真实百炼调用，非 stub）
- Macro-F1：**0.6921**
- Evidence P：**0.8062** / R：**0.7247**
- 调用失败条数：0
- 口径：不是生产准确率；须人工签发后才是处置。

### 混淆矩阵（行=gold，列=pred）

| gold \ pred | exclude | observe | suggest_report |
| --- | --- | --- | --- |
| exclude | 53 | 35 | 0 |
| observe | 0 | 22 | 22 |
| suggest_report | 0 | 0 | 88 |

- per_class：`{"exclude": {"precision": 1.0, "recall": 0.6023, "f1": 0.7518, "support": 88}, "observe": {"precision": 0.386, "recall": 0.5, "f1": 0.4356, "support": 44}, "suggest_report": {"precision": 0.8, "recall": 1.0, "f1": 0.8889, "support": 88}}`
- caveat：与 seed_extended 规则模板不同源的合成 vignette 标注集；annotation_reason 为脚本写入的标注理由，不是人工专家标注；禁止写成生产准确率。

## 能力指标占位（规则同源 stub）
- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。
- 上节为独立 vignette 集上的真实模型实验数字，禁止与 stub 机制验证混写成产品准确率。
