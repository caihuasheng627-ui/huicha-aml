# 观察 / 上报边界人工裁定

范围：主集 + 盲区 `judge_v3` 判错的观察族（`inheritance_partial` / `purpose_docs_gap` / `first_large` / `docs_pending`）。
规则：**不得为提分改金标**。仅当多数条目按调查实务看现行金标偏松时，才改 gold 并重算；若是模型把「缺材料 + 口述不一」当成异常节奏，则保持 gold，把约束写进 `judge_v4` 草案。

导出条数：**16**。

## 总裁定

16 条全部是观察族被升为 `suggest_report`，没有排除↔上报对角。

| 族 | 条数 | 现行金标 | 调查实务裁定 | 处理 |
| --- | ---: | --- | --- | --- |
| `inheritance_partial` | 6 | observe：继承材料不齐、口述用途变更，流水无异常节奏 | 口述矛盾值得记疑点，但在无快进快出/对手不可核时，实务仍应先补公证书与分配文书，而不是直接建议上报 | **维持 gold**；模型偏严 |
| `docs_pending` | 6 | observe：他行转入 + 继承材料缺页，无异常节奏 | 同上。账户历史以养老金为主，更支持「待补证」而不是类型学命中 | **维持 gold**；模型偏严 |
| `first_large` | 4 | observe：新开户首笔大额、对手可查、书面未齐 | 新户首笔大额是关注点，但对手工商存续且无夜间连转时，实务先补购销凭证；部分 raw 还编了「快进快出/拆分」 | **维持 gold**；模型偏严并偶发过度类型学 |
| `purpose_docs_gap` | 0 | observe | 本批无判错 | 无需改 |

**结论**：多数条目上现行金标并不偏松，偏的是模型把「材料缺口 + 陈述不一致」读成上报档。不改 gold，不重算主表。该边界进入第 4 步 `judge_v4`：缺材料且无异常节奏必须 observe；陈述不一致单独记疑点，不自动升档。

## 逐条对照

### 1. `IND-0038` · 主集 v3 · `inheritance_partial`

- 告警：遗产过户大额入账
- 摘要：账户于2026-06-17入账 120 万，客户称遗产分配，但公证书缺页。
- 叙事项：账户历史以养老金为主，偶发亲友转入；大额入账后用途说明在「治丧」与「购房」间变更
- 标注理由：[inheritance_partial] 继承材料不完整，用途说明前后不一致，需补证。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['遗产继承公证书完整件', '购房合同或治丧费用凭证'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.72, "typologies": ["遗产继承资金用途不明", "资金来源与用途说明不一致"], "supporting_evidence_ids": ["TX-60E62FBE65", "IX-34099B94C5", "TX-B82E4D439F", "TX-0D2836EEAC", "TX-88966D79CD"], "contradicting_evidence_ids": ["IX-AC5A860879"], "missing_evidence": ["遗产继承公证书完整件", "购房合同或治丧费用凭证"], "rationale": [{"text": "账户历史以养老金为主，月均入账约4000元，与同行基线相符，但2026-06-17突然入账120万元遗产分配，金额为平时月入
```

</details>

### 2. `IND-0071` · 主集 v3 · `inheritance_partial`

- 告警：遗产过户大额入账
- 摘要：账户于2026-04-07入账 26 万，客户称遗产分配，但公证书缺页。
- 叙事项：账户历史以养老金为主，偶发亲友转入；大额入账后用途说明在「治丧」与「购房」间变更；客户提交部分公证书复印件，缺继承权完整页
- 标注理由：[inheritance_partial] 继承材料不完整，用途说明前后不一致，需补证。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['完整继承权公证书', '遗产分配协议或遗嘱', '资金用途证明文件'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["遗产继承资金用途不明", "资金来源证明不完整", "资金用途说明前后矛盾"], "supporting_evidence_ids": ["TX-A6939D431A", "IX-D77A9F447E", "IX-76FA9AF9E0", "TX-843882215B"], "contradicting_evidence_ids": ["IX-6379E30F36", "TX-E716FF3517", "TX-46A332FCB7", "TX-C297F525F6"], "missing_evidence": ["完整继承权公证书", "遗产分配协议或遗嘱", "资金用途证明文件"], "rationale": [{"text": "账户历史以养老金为
```

</details>

### 3. `IND-0093` · 主集 v3 · `inheritance_partial`

- 告警：遗产过户大额入账
- 摘要：2026-06-24 收到 85 万，仅有部分公证复印件。
- 叙事项：大额入账后用途说明在「治丧」与「购房」间变更；客户提交部分公证书复印件，缺继承权完整页；柜面曾口头称亲属关系，系统白名单未登记
- 标注理由：[inheritance_partial] 继承材料不完整，用途说明前后不一致，需补证。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['完整继承权公证书', '遗产分配协议或遗嘱', '资金用途证明文件'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["遗产继承资金用途不明", "资金来源证明不完整", "大额入账后用途说明前后矛盾"], "supporting_evidence_ids": ["TX-BDFEFCD5CF", "IX-27DB5D477C", "IX-C752376CAD", "IX-21504992CF", "KB-REG-01"], "contradicting_evidence_ids": ["TX-86A5259811", "TX-0B11805A43", "TX-3D3F5960E0"], "missing_evidence": ["完整继承权公证书", "遗产分配协议或遗嘱", "资金用途证明文件"], "rationale": [{"text": "账户收到85万元遗产
```

</details>

### 4. `IND-0170` · 主集 v3 · `inheritance_partial`

- 告警：遗产过户大额入账
- 摘要：2026-04-03 收到 26 万，仅有部分公证复印件。
- 叙事项：柜面曾口头称亲属关系，系统白名单未登记；大额入账后用途说明在「治丧」与「购房」间变更
- 标注理由：[inheritance_partial] 继承材料不完整，用途说明前后不一致，需补证。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['遗产继承公证书', '亲属关系证明', '遗产分配协议'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["遗产继承资金无有效证明", "用途说明前后矛盾"], "supporting_evidence_ids": ["TX-B630266BA2", "IX-6956C43110", "IX-BE281E38B3", "KB-REG-01"], "contradicting_evidence_ids": ["TX-1AA4E9780C", "TX-78CA9F72AB", "TX-7F44A939BC"], "missing_evidence": ["遗产继承公证书", "亲属关系证明", "遗产分配协议"], "rationale": [{"text": "26万元遗产分配入账仅有部分公证复印件，且柜面口头称亲属关系但系统白名单未登记，权利证明不完整，支持
```

</details>

### 5. `IND-0192` · 主集 v3 · `inheritance_partial`

- 告警：遗产过户大额入账
- 摘要：声称遗产过户到账 120 万，缺完整权利证明。
- 叙事项：客户提交部分公证书复印件，缺继承权完整页；大额入账后用途说明在「治丧」与「购房」间变更；柜面曾口头称亲属关系，系统白名单未登记
- 标注理由：[inheritance_partial] 继承材料不完整，用途说明前后不一致，需补证。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['完整继承权公证书', '被继承人死亡证明及关系证明', '遗产分配协议或法院文书'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["遗产继承资金真实性存疑", "资金用途解释前后矛盾", "亲属关系证明缺失"], "supporting_evidence_ids": ["TX-5398C8DEE4", "IX-3105AA25FC", "IX-D988432A9C", "IX-9DB6906024", "KB-PROC-01"], "contradicting_evidence_ids": ["TX-9C346D8FEA", "TX-6B80219C64", "TX-15786DEE41"], "missing_evidence": ["完整继承权公证书", "被继承人死亡证明及关系证明", "遗产分配协议或法院文书"], "rationale": [{"text": "120万元
```

</details>

### 6. `IND-0203` · 主集 v3 · `inheritance_partial`

- 告警：遗产过户大额入账
- 摘要：账户于2026-04-03入账 48 万，客户称遗产分配，但公证书缺页。
- 叙事项：柜面曾口头称亲属关系，系统白名单未登记；客户提交部分公证书复印件，缺继承权完整页；大额入账后用途说明在「治丧」与「购房」间变更；账户历史以养老金为主，偶发亲友转入
- 标注理由：[inheritance_partial] 继承材料不完整，用途说明前后不一致，需补证。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['完整继承权公证书', '遗产分配协议或遗嘱', '资金用途证明文件'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.72, "typologies": ["遗产继承资金无有效权利证明", "资金来源解释前后矛盾"], "supporting_evidence_ids": ["TX-95FA3F0B57", "IX-F5BBF23C0D", "IX-EB1DF8C554", "IX-EE86A8BB40", "KB-REG-01"], "contradicting_evidence_ids": ["IX-97ECE2804E", "TX-BFEF5D7F80", "TX-6216F744D7", "TX-9C0B9BA75A"], "missing_evidence": ["完整继承权公证书", "遗产分配协议或遗嘱", "资金用途证明文件"], "rationale": [{"text": "账户收到48
```

</details>

### 7. `BLD-0021` · 盲区 v3 · `first_large`

- 告警：大额转账待核
- 摘要：2026-04-06 单笔支出 18 万，仅有口头货款说明。
- 叙事项：对手工商存续，客户只提供口头「货款」说明；开户未满 30 日即出现首笔大额对公支付
- 标注理由：[first_large] 新开户首笔大额对公支付，对手可查但书面依据未齐。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['购销合同或发票', '货物交付凭证', '客户职业及收入来源证明'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.72, "typologies": ["疑似代发工资账户被用于大额对公支付，资金性质与客户职业背景不符", "开户短期内即发生大额转账，缺乏合理经营或生活解释"], "supporting_evidence_ids": ["TX-8C382F3D21", "IX-DC34B4D2D1", "IX-5C35D2EBEC", "TX-F5D7DEBFAA", "TX-9D20353DA3", "KB-PROC-01"], "contradicting_evidence_ids": [], "missing_evidence": ["购销合同或发票", "货物交付凭证", "客户职业及收入来源证明"], "rationale": [{"text": "账户历史仅有两笔代发劳务费入账（合计约2.1万
```

</details>

### 8. `BLD-0044` · 盲区 v3 · `docs_pending`

- 告警：遗产相关大额入账
- 摘要：声称遗产到账 62 万，缺完整权利证明。
- 叙事项：入账后口头用途在「治丧」与「购房」间变更
- 标注理由：[docs_pending] 他行转入大额，继承材料不完整，尚无异常节奏。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['遗产继承公证书', '被继承人死亡证明', '遗产分配协议或法院判决书'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition":"suggest_report","confidence":0.72,"typologies":["遗产继承资金来源不明","大额资金入账用途前后矛盾"],"supporting_evidence_ids":["TX-C1915939FE","IX-3E721BC226","KB-PROC-01","KB-REG-01","KB-REG-03"],"contradicting_evidence_ids":["TX-F52F412DEE","TX-D56F9C0D1E"],"missing_evidence":["遗产继承公证书","被继承人死亡证明","遗产分配协议或法院判决书"],"rationale":[{"text":"账户收到62万元大额转账，远超该账户养老金月均入账约3000元的正常水平，且与同行典型月入8000元相比偏离78倍，构成异常节奏，支持上
```

</details>

### 9. `BLD-0099` · 盲区 v3 · `docs_pending`

- 告警：遗产相关大额入账
- 摘要：入账 62 万后未能当场补齐文书全文。
- 叙事项：柜面口头称亲属关系，系统未登记；账户历史以养老金为主，偶发亲友转入；客户提交部分继承材料复印件，缺完整权利页；入账后口头用途在「治丧」与「购房」间变更
- 标注理由：[docs_pending] 他行转入大额，继承材料不完整，尚无异常节奏。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['完整继承权证明文件', '亲属关系公证书', '资金来源合法用途说明'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["遗产继承资金无有效权利证明", "资金来源解释前后矛盾"], "supporting_evidence_ids": ["TX-15792A3DDE", "IX-3BFD61A102", "IX-44898F43E2", "IX-AFB46985D9", "KB-REG-01"], "contradicting_evidence_ids": ["IX-9F35742828", "TX-D41CA7C28F", "TX-998AC05F6C"], "missing_evidence": ["完整继承权证明文件", "亲属关系公证书", "资金来源合法用途说明"], "rationale": [{"text": "62万元大额转账（TX-15792A3DDE
```

</details>

### 10. `BLD-0176` · 盲区 v3 · `docs_pending`

- 告警：遗产相关大额入账
- 摘要：账户于2026-08-22入账 62 万，客户称遗产分配，材料缺页。
- 叙事项：柜面口头称亲属关系，系统未登记；客户提交部分继承材料复印件，缺完整权利页；入账后口头用途在「治丧」与「购房」间变更
- 标注理由：[docs_pending] 他行转入大额，继承材料不完整，尚无异常节奏。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['遗产继承公证书', '亲属关系证明', '遗产分配协议'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.72, "typologies": ["遗产继承资金异常", "资金来源解释不一致"], "supporting_evidence_ids": ["TX-6D7D404F53", "IX-AE468F2139", "IX-D95A8D7EEA", "IX-4360D758CD", "KB-REG-01"], "contradicting_evidence_ids": ["TX-098031F39B", "TX-0E2367B3E3"], "missing_evidence": ["遗产继承公证书", "亲属关系证明", "遗产分配协议"], "rationale": [{"text": "账户收到62万元大额转账，远超该账户养老金月均入账约3000-4000元的正常水平，且与同行典型月入80
```

</details>

### 11. `BLD-0186` · 盲区 v3 · `first_large`

- 告警：大额转账待核
- 摘要：账户转出 35 万，结算单承诺后补。
- 叙事项：对手工商存续，客户只提供口头「货款」说明；月度劳务费入账稳定；开户未满 30 日即出现首笔大额对公支付
- 标注理由：[first_large] 新开户首笔大额对公支付，对手可查但书面依据未齐。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['购销合同或发票', '对手方尽调材料'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["疑似过渡账户", "大额资金快进快出"], "supporting_evidence_ids": ["TX-EE5BAED0D8", "IX-0B20C68F0B", "IX-9E214BDDCE", "KB-REG-01", "KB-REG-03"], "contradicting_evidence_ids": ["IX-4AA553828E", "TX-E3B153C322", "TX-0531C3D261"], "missing_evidence": ["购销合同或发票", "对手方尽调材料"], "rationale": [{"text": "账户开户未满30日即发生35万元大额对公转账，远超其受雇身份月均1.5万元入账水平，资金规模与职业背景
```

</details>

### 12. `BLD-0187` · 盲区 v3 · `docs_pending`

- 告警：遗产相关大额入账
- 摘要：账户于2026-03-28入账 48 万，客户称遗产分配，材料缺页。
- 叙事项：客户提交部分继承材料复印件，缺完整权利页；柜面口头称亲属关系，系统未登记；入账后口头用途在「治丧」与「购房」间变更
- 标注理由：[docs_pending] 他行转入大额，继承材料不完整，尚无异常节奏。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['完整继承权证明文件', '亲属关系公证材料', '资金用途说明及佐证凭证'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["遗产继承资金无有效权利证明", "资金用途陈述前后矛盾", "大额入账与账户历史流水模式显著偏离"], "supporting_evidence_ids": ["TX-41C39E8ED6", "IX-F6F3431B5E", "IX-F695A48329", "IX-BC73888999", "KB-REG-01", "KB-REG-03"], "contradicting_evidence_ids": ["TX-8BA46EB8C3", "TX-49E4C45903"], "missing_evidence": ["完整继承权证明文件", "亲属关系公证材料", "资金用途说明及佐证凭证"], "rationale": [{"text": "账户历
```

</details>

### 13. `BLD-0197` · 盲区 v3 · `first_large`

- 告警：大额转账待核
- 摘要：2026-03-12 单笔支出 35 万，仅有口头货款说明。
- 叙事项：开户未满 30 日即出现首笔大额对公支付；对手工商存续，客户只提供口头「货款」说明
- 标注理由：[first_large] 新开户首笔大额对公支付，对手可查但书面依据未齐。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['购销合同', '货物交付凭证', '客户职业及收入证明'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{
  "disposition": "suggest_report",
  "confidence": 0.72,
  "typologies": ["疑似拆分交易规避监测", "疑似无真实经营背景的大额资金转移"],
  "supporting_evidence_ids": ["TX-BF248C2029", "IX-B704B51E81", "IX-AEF9955257", "TX-6F17A032E7", "TX-9D145A6898", "KB-PROC-01"],
  "contradicting_evidence_ids": ["ACC-298826"],
  "missing_evidence": ["购销合同", "货物交付凭证", "客户职业及收入证明"],
  "rationale": [
    {
      "text": "账户开户未满30日即发生35万元大额
```

</details>

### 14. `BLD-0198` · 盲区 v3 · `docs_pending`

- 告警：遗产相关大额入账
- 摘要：声称遗产到账 62 万，缺完整权利证明。
- 叙事项：入账后口头用途在「治丧」与「购房」间变更；账户历史以养老金为主，偶发亲友转入；柜面口头称亲属关系，系统未登记
- 标注理由：[docs_pending] 他行转入大额，继承材料不完整，尚无异常节奏。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.72 · missing=['遗产继承公证书', '亲属关系证明', '遗产分配协议'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.72, "typologies": ["遗产继承资金无合法来源证明", "资金用途前后矛盾", "大额资金入账与账户历史模式显著不符"], "supporting_evidence_ids": ["TX-17BD693AC1", "IX-8283E3BE75", "IX-E2B4176ED8", "KB-REG-01", "KB-REG-03"], "contradicting_evidence_ids": ["IX-8A3860A016", "TX-C4E6FC687E", "TX-F189280857"], "missing_evidence": ["遗产继承公证书", "亲属关系证明", "遗产分配协议"], "rationale": [{"text": "62万元遗产入账仅有口头声称
```

</details>

### 15. `BLD-0219` · 盲区 v3 · `first_large`

- 告警：大额转账待核
- 摘要：2026-09-15 单笔支出 35 万，仅有口头货款说明。
- 叙事项：对手工商存续，客户只提供口头「货款」说明；开户未满 30 日即出现首笔大额对公支付
- 标注理由：[first_large] 新开户首笔大额对公支付，对手可查但书面依据未齐。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.62 · missing=['购销合同或发票', '对手方工商信息及交易背景说明', '客户收入来源证明'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.62, "typologies": ["大额资金与身份不符", "开户初期即发生大额交易", "资金用途缺乏有效凭证"], "supporting_evidence_ids": ["TX-CC82A4BA7E", "IX-9084507770", "IX-3A8D43EF8D", "TX-D15AA68237", "TX-3A55EFBBCB"], "contradicting_evidence_ids": ["ACC-675806"], "missing_evidence": ["购销合同或发票", "对手方工商信息及交易背景说明", "客户收入来源证明"], "rationale": [{"text": "客户为受雇个人，账户历史仅两笔合计约2万元的代发劳务费入账，与35万元单笔对公转账
```

</details>

### 16. `BLD-0220` · 盲区 v3 · `docs_pending`

- 告警：遗产相关大额入账
- 摘要：2026-09-14 收到 35 万，仅有部分复印件。
- 叙事项：入账后口头用途在「治丧」与「购房」间变更；客户提交部分继承材料复印件，缺完整权利页
- 标注理由：[docs_pending] 他行转入大额，继承材料不完整，尚无异常节奏。

| 列 | 内容 |
| --- | --- |
| 现行金标 | `observe`：无清晰异常节奏，缺闭合材料，应观察补证 |
| 模型输出 | `suggest_report` · confidence=0.65 · missing=['完整继承权利证明文件', '遗产分配协议或公证书', '资金来源方身份及关系证明'] |
| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |
| 是否改 gold | 否 |

<details><summary>raw 摘录</summary>

```
{"disposition": "suggest_report", "confidence": 0.65, "typologies": ["遗产继承资金真实性存疑", "资金来源解释不一致"], "supporting_evidence_ids": ["TX-87D0F95249", "IX-A234F4B86B", "IX-3A691EF556", "KB-REG-01", "KB-REG-03"], "contradicting_evidence_ids": ["TX-63D6D8950B", "TX-3D50066385"], "missing_evidence": ["完整继承权利证明文件", "遗产分配协议或公证书", "资金来源方身份及关系证明"], "rationale": [{"text": "35万元大额入账与账户日常养老金流水（月均3000-4000元）形成显著反差，金
```

</details>

## 复现

```bash
python3 experiments/benchmark/export_boundary.py
```
