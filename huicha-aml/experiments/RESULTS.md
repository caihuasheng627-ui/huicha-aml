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
