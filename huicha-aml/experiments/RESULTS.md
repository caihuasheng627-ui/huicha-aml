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

## 独立集 / 真实模型（v2 协议 · 待重跑）

- 协议：`judge_v2` → `normalize_judge` → `verify_judge` → `apply_guardrails`
- 标注集：`independent_set.json`（n=240，**n_unique=240**，source=`narrative_vignette_v2_combinatorial`）
- 离线基线（无需密钥）：always_suggest_report Macro-F1 **0.2082**；keyword_match Macro-F1 **0.867**
- 真实模型数字：**待你在本机执行** `python experiments/benchmark.py --real` 后写入
- 原始输出将落盘 `experiments/benchmark/runs/<timestamp>.jsonl`
- 口径：不是生产准确率；须人工签发。已去除标签泄漏；仍为合成 vignette。

### v1 结果已降级（勿再引用为模型能力）

- 原 Macro-F1≈0.69 等数字仅作「API 能打通」记录
- 已知硬伤：n_unique≈10、标签泄漏、SYSTEM 贴合测试集叙事、未走产品 Judge、解析失败并入 observe、Evidence gold 含空 KYC
- 详见 `RESULTS.json` → `independent_real_model_v1_deprecated`

## 能力指标占位（规则同源 stub）
- golden_set / test_set 仍保留框架槽位；test_set 为空时能力指标 Not evaluated yet。
- 上节为独立 vignette × 产品 Judge 的实验数字，禁止与 stub 机制验证混写成产品准确率。
