# 调查人效与外部复核协议

**在本文件对应的记录表填入真实样本之前，PPT、报告、口播都不得出现任何「效率提升 xx%」。**  
`python experiments/efficiency.py` 在记录为空时会拒绝计算提升百分比。

---

## A. 改稿对照（人效）

### 目的

验证工作台是否把「从零写四段底稿」变成「改稿」，而不是证明模型更准。

### 样本

使用工作台示例案，不要用模板精标库刷 n：

| case_id | 标签 | 预期档位（仅组织者可见，被试不可见） |
|---------|------|--------------------------------------|
| ALT-A-20260910 | 排除 | exclude |
| ALT-B-20260910 | 拆分 | suggest_report |
| ALT-C-20260910 | 归集 | suggest_report |
| ALT-F-20260910 | 观察 | observe |
| ALT-L-20260910 | 多层 | suggest_report |
| ALT-D-20260910 | 已登记亲属（若库中有） | exclude |

每名被试做 3 案即可。全组覆盖上表即可交差，不要求每人做完 6 案。

### 条件

- `human_only`：关闭慧查agent（实验模式），只看流水、KYC、规则对照，手写四段草稿。  
- `human_plus_huicha`：正常模式生成草稿后，只允许改稿、补意见、签发。

同一人不要先做 plus 再做 only 的同一案。组间交叉：一半人 only 做 A/B/L，plus 做 C/F；另一半对调。

### 记录字段

写入 `experiments/efficiency_records.csv`（表头已建好）：

| 字段 | 含义 |
|------|------|
| investigator_id | 被试代号，不要写真名 |
| case_id | 如上 |
| condition | `human_only` 或 `human_plus_huicha` |
| investigation_time_sec | 从打开案件到交卷的秒数 |
| evidence_missing | 交卷稿相对清单仍缺的材料条数 |
| wrong_judgment | 三档是否与组织者金标不同，0/1。金标仅组织者见 |
| report_completeness | 四段要素填齐比例，0–1 |
| data_note | 固定填 `synthetic-study` |

### 怎么报

只报：样本量、两条件的时间中位数、要素完整率中位数。  
可以写「本轮教室对照 n=__，改稿组中位耗时低于手写组」。  
禁止外推到生产调查岗，禁止在 n&lt;8 时做显著性声明。

汇总：

```bash
cd huicha-aml
python experiments/efficiency.py
```

---

## B. 外部专家复核（档位，不是准确率）

`benchmark/gold_review_sheet.md` 是盲评表。仓库里已有的 `gold_review_labels.json` 是**实验作者自洽**，不得写成外部一致率。

请一位未参加开发的人（指导老师、有反洗钱/合规实习者均可）：

1. 只看 `gold_review_sheet.md`，不看 gold、不看 RESULTS。  
2. 把档位填进新文件 `benchmark/gold_review_labels.external.json`（字段与 `gold_review_labels.json` 相同）。  
3. 运行 `python experiments/benchmark/score_gold_review.py`（若脚本需改路径，以脚本内说明为准）。

对外只说：「独立阅读叙事族后的档位一致率」，并写明复核人身份与 n。不要和合成 Macro-F1 加在一起平均。
