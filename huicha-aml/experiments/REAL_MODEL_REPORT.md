# 循证慧查 · 真实模型测试报告（v2 全量）

**日期**：2026-09-12  
**标签**：独立集 / 真实模型 / 产品 Judge 流水线  
**模型**：`deepseek-v4-flash-0731`（阿里云百炼）  
**数据**：`narrative_vignette_v2_combinatorial`（n=240，n_unique=240）  
**日志**：`experiments/benchmark/runs/20260912T132445Z.jsonl`

---

## 0. 诚实声明（必读）

1. 本报告为**合成 vignette**上的实验对照，标注理由由脚本写入，**不是**人工专家标注。  
2. **禁止**写成生产调查准确率或报送依据；Agent 建议须调查员签发。  
3. v1（Macro-F1≈0.69）因「约 10 个唯一输入 + 标签泄漏 + 自写 prompt」已降级，**不得与本报告混比**。  
4. 工作台面板「模板精标 ≈80」是规则同源演示集，与本独立集无关。

---

## 1. 实验配置

| 项 | 值 |
| --- | --- |
| 协议 | `judge_v2` → `normalize_judge` → `verify_judge` → `apply_guardrails` |
| 命令 | `python experiments/benchmark.py --real` |
| 计分条数 | 240 / 240（parse_failures=0，call_errors=0） |
| 证据契约通过率 | 1.0 |
| Gold 分布 | exclude 87 · observe 44 · suggest_report 109 |

---

## 2. 总结果对照

| 方法 | Macro-F1 | Accuracy | 说明 |
| --- | ---: | ---: | --- |
| **产品 Judge（本跑）** | **0.1686** | 0.2292 | 真实模型 |
| 基线 always_suggest_report | 0.2082 | 0.4542 | 无信息下限 |
| 基线 keyword_match | 0.8670 | 0.8542 | 弱规则上限（合成文本表面线索） |

**结论一句**：在去泄漏的独立合成集上，当前 Judge **低于无信息「全上报」基线的 Macro-F1**，说明问题主要是**三档边界塌缩为「观察」**，不是「随机乱报」。

---

## 3. 混淆矩阵

| gold \ pred | exclude | observe | suggest_report | 行合计 |
| --- | ---: | ---: | ---: | ---: |
| exclude | 0 | 87 | 0 | 87 |
| observe | 0 | 44 | 0 | 44 |
| suggest_report | 0 | 98 | 11 | 109 |
| **列合计** | **0** | **229** | **11** | **240** |

### 误差结构

- **排除档全灭**：87 条金标排除全部被判观察（召回 0）。  
- **观察档「虚高」**：金标观察 44 条全对，但模型总共判了 229 条观察 → 精确率只有 0.19。  
- **上报档极度保守**：109 条金标上报仅 11 条命中（召回 ≈10.1%）；精确率 1.0（判上报的都对），以 suggest_report 为正类的 **FPR=0**。  
- **无危险对角**：没有出现 exclude → suggest_report。

---

## 4. 分档 Precision / Recall / F1

| 标签 | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| exclude | 0.0000 | 0.0000 | 0.0000 | 87 |
| observe | 0.1921 | 1.0000 | 0.3223 | 44 |
| suggest_report | 1.0000 | 0.1009 | 0.1833 | 109 |

---

## 5. Evidence P&R

| 侧 | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| 支持证据 | 0.3736 | 0.8397 | 0.5172 |
| 反证证据 | 0.0000 | 0.0000 | 0.0000 |

解读：模型较常点到金标支持证据（召回尚可），但精确率一般（多引噪声）；反证侧基本未按协议使用 `contradicting_evidence_ids`（或金标反证稀疏 + 模型未填）。

---

## 6. 按叙事族（tag）

| 模式 | 代表 tag | 现象 |
| --- | --- | --- |
| 观察族「全中」 | `inheritance_partial`, `purpose_docs_gap` | acc=1.0（与全局「默认观察」一致） |
| 排除族「全失」 | `payroll_batch`, `insurance_claim`, `gov_subsidy`, `escrow_release` | acc=0 |
| 上报族「偶发命中」 | `crypto_onramp` 相对略好；`atm_smurf`/`nested_shell_loan` 等接近 0 | 多数压成观察 |

完整 by_tag 见 `RESULTS.json` → `independent_real_model.by_tag`。

---

## 7. 对产品与答辩的含义

### 可以说

- v2 实验协议成立：唯一输入 240、无标签泄漏、产品 Judge 契约、原始输出可审计。  
- 系统在本集上呈现**强保守偏置**（倾向继续观察），误报上报风险极低。  
- 与 keyword 基线的巨大落差，说明「有表面词可分」时模型仍未形成可操作判据——改进方向清晰。

### 不可以说

- 「准确率 22.9% / Macro-F1 16.9%」为生产能力。  
- 「比 v1 的 0.69 退步了」——两套实验不可比。  
- 「已经超过关键词规则」——事实相反。

### 建议的下一步（提分手段，基于本真实诊断）

1. 在 `judge_v2` 中写清三档可操作边界：合理解释充分→exclude；缺材料但无清晰异常节奏→observe；异常节奏且无合理解释→suggest_report。  
2. 要求先输出 `missing_evidence` / `rationale` 再给 disposition。  
3. 用与测试集无关的少量示例（可来自路演案，并注明同源）。  
4. 对 observe 塌缩做专项冒烟集，再全量复测。

---

## 8. 产物索引

| 文件 | 内容 |
| --- | --- |
| `RESULTS.md` §B | 结果摘要 |
| `RESULTS.json` → `independent_real_model` | 结构化全量 |
| `SELF_TEST_PLAYBOOK.md` | 复现流程 |
| `benchmark/independent_set.json` | 数据 |
| `benchmark/runs/20260912T132445Z.jsonl` | 逐条 raw 输出 |
