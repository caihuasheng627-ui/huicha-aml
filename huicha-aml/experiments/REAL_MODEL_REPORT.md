# 循证慧查 · 真实模型测试报告（v3 集 · judge_v2 → judge_v3 消融）

**日期**：2026-09-12  
**标签**：独立集 / 真实模型 / 产品 Judge 流水线（`enrich_judge` 直调）  
**模型**：`deepseek-v4-flash-0731`（阿里云百炼）  
**数据**：`narrative_vignette_v3_rules_layer`（n=240，n_unique=240；gold 分布 exclude 88 · observe 44 · suggest_report 108）  
**日志**：`experiments/benchmark/runs/20260912T144147Z_judge_v2.jsonl`（对照组）· `experiments/benchmark/runs/20260912T151253Z_judge_v3.jsonl`（实验组）

---

## 0. 诚实声明（必读）

1. 本报告为**合成 vignette**上的实验对照，标注理由由脚本写入，**不是**人工专家标注。  
2. **禁止**写成生产调查准确率或报送依据；Agent 建议须调查员签发。  
3. v1（Macro-F1≈0.69，泄漏假集）与 v2 集（Macro-F1 0.1686，见 §1.1）均已降级，**不得与本报告混比**。  
4. judge_v3 的三档标准里例举的异常节奏（短时多点取现回流、多层递减过桥、关联对倒闭环、现金→兑换商、分散归集→集中外转）**与本集 5 个上报族高度重合**——这是常见类型学，不是抄测试集，但意味着 0.97 是「标准覆盖了测试族」条件下的乐观估计；例举之外的类型学需要另做 hold-out（见 §7）。  
5. 叙事项的 `polarity`（support/counter/context）由生成器按产品规则层的语义标注后**作为输入交给 Judge**，与产品路径中 `analyst_rules` 输出极性一致；它是产品输入的一部分，但也确实是强信号，读数时须知悉。

---

## 1. 这一版改了什么

### 1.1 实验侧（先做，不碰产品代码）——修复 v2 集的有效性问题

| v2 集问题 | v3 集处理 |
| --- | --- |
| 只有 observe 族携带 `missing_evidence` 输入（标签泄漏） | **不再传 `missing_evidence`**（产品 `enrich_judge` 本来也不传） |
| findings 全部 `polarity=context`、`code=vignette-fact`，无规则层 | 先按族生成**真实结构流水**，再调产品 `analyst_rules.analyze()`：ATM 族触发 `night-out`，对倒/过桥族触发 `layering`，归集族触发 `funnel`，存现族触发 `structuring`；叙事项作为 `case-note` finding 带 support/counter/context 极性，排除族必有 counter 开脱证据 |
| `peer_note`/客户名/客户摘要/交易备注含「合成/占位」 | 全部替换为中性业务文本；`kb_hits` 由 `knowledge.retrieve_for_alert(alert_type, industry)` 检索 |
| 证据编号 `EV-` 被产品 `enrich_judge` 过滤，Judge 只看到空编号列表 | 流水 `TX-`、叙事项 `IX-`、知识 `KB-`，与产品契约一致 |
| benchmark 自行拼 context 直调 `chat`（含非产品字段 `evidence_bundle`/`case_summary`） | 直接调用 `enrich_judge(db=None, ...)`，后处理 normalize → verify → guardrails 不变 |

新增读数：confidence 直方图 / 去重取值数 / 标准差；observe 预测中带非空 `missing_evidence` 的比例；证据 P/R 只在叙事项 `IX-` 上计算（TX/KB 引用另计引用率）。以上不变量已固化为 `backend/tests/test_independent_benchmark_set.py`（4 条）。

### 1.2 产品侧（后做，唯一影响线上行为的改动）——`judge_v2` → `judge_v3`

在 `judge_v2` 的引用契约之上，加入可操作判定标准：

- **exclude**：资金来源与去向均有完整合理解释（工资表、赔付书、财政批次、监管放款指令、网签合同等已与流水勾稽），且所有干扰点已解释或与本案无关；材料已足以闭合时不得因「可再补材料」降为 observe。  
- **observe**：流水无清晰异常节奏，但缺少能闭合资金链条的关键材料（合同、公证书、用途说明、发票）；**必须列出 `missing_evidence`**。  
- **suggest_report**：流水呈现异常节奏且无经营/生活解释；**即使材料不完整也不得降为 observe**。  
- 一致性：`missing_evidence` 为空不得输出 observe（除非 rationale 明确写「无异常节奏且无待补材料」并说明为何仍不能排除）；每条 rationale 写明证据把结论推向哪一档；confidence 随证据强弱真实变化。

`prompt_version("judge")` → `judge_v3`；`enrich_judge` 新增 `prompt_kind` 覆盖参数（仅供实验消融，产品路径始终用 `prompt_version`），缓存键随版本变化。

---

## 2. 消融结果（同一 v3 集、同一模型、同一后处理；唯一变量 = prompt）

| 指标 | `judge_v2`（对照） | `judge_v3`（实验） | 变化 |
| --- | ---: | ---: | ---: |
| **Macro-F1** | **0.3867** | **0.9662** | +0.5795 |
| Accuracy | 0.4557 | 0.9745 | +0.5188 |
| exclude 召回 | 0.0000 | 1.0000 | +1.00 |
| observe 召回 | 0.9773 | 0.8636 | −0.11 |
| suggest_report 召回 | 0.6190 | 1.0000 | +0.38 |
| suggest_report 精确率 | 0.9848 | 0.9450 | −0.04 |
| Evidence 支持侧 P / R（IX- 叙事项） | 0.7023 / 0.6113 | 0.7644 / 0.8640 | +0.06 / +0.25 |
| Evidence 反证侧 P / R | 0.0870 / 0.3077 | 0.3562 / 0.5000 | +0.27 / +0.19 |
| verify 通过率 | 1.0 | 1.0 | — |
| parse_failures（模型输出 JSON 结构不完整，非截断） | 3 | 5 | +2 |
| confidence 标准差 / 去重取值数 | 0.0949 / 9 | 0.1417 / 7 | 更分散 |
| confidence 按 gold 均值（exclude / observe / report） | 0.70 / 0.55 / 0.70 | 0.85 / 0.48 / 0.79 | 三档拉开 |
| observe 预测带非空 missing_evidence | 1.0 | 1.0 | — |
| exclude 预测带非空 missing_evidence | （无 exclude 预测） | 0.0 | 契约成立 |
| rationale 写明推向哪一档的样本比例 | 0.131 | 1.000 | 契约成立 |

基线（同一集）：always_suggest_report Macro-F1 = 0.2069；keyword_match = 0.8031。

**一句话结论**：仅补回规则层并去泄漏（B 步），`judge_v2` 从 0.17 升到 0.39 但排除档仍全灭（88/88 → observe）；再加上 `judge_v3` 的三档标准（A 步），排除档召回 0 → 1.0、上报档召回 0.62 → 1.0，Macro-F1 0.39 → 0.97，越过 keyword 基线 0.80。两步的贡献可分离：**规则层修复了「Judge 看不见结构」，prompt 标准修复了「看见了也不敢下结论」**。

---

## 3. 混淆矩阵

### judge_v2（对照，n_scored=237）

| gold \ pred | exclude | observe | suggest_report |
| --- | ---: | ---: | ---: |
| exclude | 0 | 88 | 0 |
| observe | 0 | 43 | 1 |
| suggest_report | 0 | 40 | 65 |

- 排除档全灭：模型在 rationale 里已写出「与工资表一致、符合发薪特征」，但结论仍给 observe 并要求「补工资表原件」——典型的「可再补材料 ⇒ 观察」塌缩。  
- 上报档 40/105 压成 observe，集中在 `nested_shell_loan`（14）与 `invoice_circular`（15）：规则层已给 `layering` support finding，模型仍以「借款合同未见」为由降档。

### judge_v3（实验，n_scored=235）

| gold \ pred | exclude | observe | suggest_report |
| --- | ---: | ---: | ---: |
| exclude | 88 | 0 | 0 |
| observe | 0 | 38 | 6 |
| suggest_report | 0 | 0 | 103 |

- 唯一误差方向：`inheritance_partial` 6/22 被判 suggest_report（理由为「入账为月均养老金的 100–300 倍且用途说明前后矛盾，支持上报」）。这类「大额突增 + 说法反复」在真实调查里本就处于 observe/上报边界，误差方向是**偏严**而非漏报。  
- 无 exclude ↔ suggest_report 的危险对角。

---

## 4. 分档 Precision / Recall / F1（judge_v3）

| 标签 | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| exclude | 1.0000 | 1.0000 | 1.0000 | 88 |
| observe | 1.0000 | 0.8636 | 0.9268 | 44 |
| suggest_report | 0.9450 | 1.0000 | 0.9717 | 103 |

---

## 5. 契约类读数

| 项 | judge_v2 | judge_v3 |
| --- | --- | --- |
| confidence 直方图 [0,.2)/[.2,.4)/[.4,.6)/[.6,.8)/[.8,1] | 0 / 0 / 71 / 146 / 20 | 0 / 0 / 38 / 52 / 145 |
| 最常见取值 | 0.55×71、0.72×47、0.75×35 | 0.85×92、0.82×51、0.45×38 |
| observe 预测 avg missing 条数 | 2.96 | 2.82 |
| suggest_report 预测带 missing 比例 | 1.0 | 0.17 |
| 被 sanitize 掉的编号样 missing 条目 | 0 | 0 |
| 引用过 TX- 编号的样本比例 | 0.996 | 1.0 |

confidence 仍偏「几个档位值」（去重取值 7–9 个），但 v3 的三档均值拉开到 0.85 / 0.48 / 0.79，且 observe 预测全部落在 0.45–0.62——**不再是所有样本一个数**，可用于分流但不是校准概率。

---

## 6. 按叙事族（judge_v3）

| gold | tag | acc |
| --- | --- | ---: |
| exclude | payroll_batch / insurance_claim / gov_subsidy / escrow_release | 1.0 / 1.0 / 1.0 / 1.0 |
| observe | purpose_docs_gap | 1.0 |
| observe | inheritance_partial | 0.727 |
| suggest_report | atm_smurf / invoice_circular / crypto_onramp / nested_shell_loan / crowdfund_layering | 1.0 / 1.0 / 1.0 / 1.0 / 1.0 |

对照 judge_v2：四个 exclude 族 acc 全 0；`invoice_circular` 0.32、`nested_shell_loan` 0.26。完整 by_tag 见 `RESULTS.json` → `independent_real_model_runs.<prompt>.by_tag`。

---

## 7. 对产品与答辩的含义

### 可以说

- 实验协议成立：唯一输入 240、无 `missing_evidence` 泄漏、Judge 输入与产品 bundle 同构（规则层 + 极性 + TX/IX/KB 编号）、直调 `enrich_judge`、原始输出可审计、消融变量唯一。  
- `judge_v3` 的三档标准在本集上把「默认观察」偏置消除：排除档召回 0 → 1.0，上报档召回 0.62 → 1.0，无危险对角。  
- 一致性契约（observe 必列待补材料、rationale 写明档位、confidence 分档）在真实模型输出上全部成立。

### 不可以说

- 「准确率 97%」为生产能力——合成集、族数 11、标准例举覆盖了全部上报族。  
- 「比 v2 集的 0.17 提升 0.8」——两套集不可比；可比的是**同一 v3 集上** 0.39 → 0.97。  
- confidence 是校准概率。

### 下一步

1. **例举之外的类型学 hold-out**：新增 judge_v3 标准里没有例举的上报族（如贸易融资重复质押、赌博资金归集、跨境拆分汇出）与更难的排除族（合理但复杂的经营解释），只跑不改 prompt，看泛化。  
2. **inheritance_partial 边界**：6 条偏严样本做人工复核，决定是修标准（「单笔突增但来源为亲属且无外转 ⇒ observe」）还是接受偏严。  
3. **parse_failures**：两版共 8 条均为模型输出 JSON 结构不完整（finish_reason=stop，非 max_tokens 截断）；产品路径有针对性重试，benchmark 保持单独计数不并入 observe。  
4. 少量真实脱敏案由调查员标注后作为最终 hold-out（与本集无关）。

---

## 8. 产物索引

| 文件 | 内容 |
| --- | --- |
| `RESULTS.md` §B（历史）/ v3 节 / 消融节 | 结果摘要 |
| `RESULTS.json` → `independent_real_model`（最新）· `independent_real_model_runs.{judge_v2,judge_v3}` · `independent_ablation` | 结构化全量 |
| `SELF_TEST_PLAYBOOK.md` | 复现流程（含 `--prompt` 消融、`--rerender`） |
| `benchmark/build_independent_set.py` · `benchmark/independent_set.json` | 数据生成器与数据 |
| `benchmark/runs/20260912T144147Z_judge_v2.jsonl` · `benchmark/runs/20260912T151253Z_judge_v3.jsonl` | 逐条 raw 输出 |
| `backend/tests/test_independent_benchmark_set.py` | 数据集不变量 |
