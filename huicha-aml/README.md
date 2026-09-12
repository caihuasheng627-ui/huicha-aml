# 循证慧查 V2.1

**AI 负责推理，规则负责边界，证据负责事实，人负责最终决策。**

对外名称：**循证慧查**。仓库目录与环境变量仍为 `huicha-aml` / `HUICHA_*`（曾用名：工e慧查 / 慧查 AML）。

面向金融机构**反洗钱告警后调查**的证据驱动、规则约束、可审计、Human-in-the-loop 调查 Copilot（竞赛/研究原型）。

对外技术说明（供商业计划最终报告）：仓库根目录 `慧查AML-技术文档（供商业计划最终报告）.md`。

## 1. Project Overview

上游检测已经产生告警。本系统不替代监测引擎，只把告警升级为**案件（Case）**：规划调查 → 收集证据 → 规则打底风险 → 有界质疑 → 校验 Claim → 结构化报告 → **人工签发**。

数据标记为 `synthetic`。不连接真实银行，不代表生产系统。

## 2. Business Problem

告警后调查耗时长、容易确认偏误、结论难回溯。需要把「AI 生成的判断」关在证据、规则、权限和审计之内，并由人做最终金融决策。

## 3. Core Innovation

1. **Evidence Graph**：Claim → Evidence → Source，禁止无证据结论。
2. **Bounded Challenger**：主动找反证；`delta` 必须 ∈ [−0.15, +0.15]，否则 Reject。
3. **Evidence Validator**：无证据 / 假证据 / 跨案证据不得进分。调分 Claim 必须带封闭谓词，由后端在本案交易快照上重新执行，不成立则 Reject。
4. **Human-in-the-loop**：`REPORT` 不能由 Agent 执行，只能 `REPORT_REVIEW` + 人签。

## 4. System Architecture

```
Transaction / Customer / Account / Relationship
        ↓
Rule / 基线风险
        ↓
Case → Planner → Evidence Collector → Risk Analyst
        → Challenger → Evidence Validator → Risk Aggregator
        → Reporter → Human Approval → Audit Trail
```

## 5. Agent Architecture

| 角色 | 职责 | 禁止 |
| --- | --- | --- |
| Planner | 只规划白名单只读工具 | 不打分、不报送 |
| Collector | 只读取数，写入 Evidence | 不编造事实 |
| Analyst | 规则因子 + evidence_ids | 不写最终监管结论 |
| Challenger | 反证 / 正常解释 / 数据不足 | 不直接改最终分 |
| Validator | 校验 Claim 与 delta | 失败项不得进分 |
| Reporter | 结构化草稿 + 法规引用 | 不自动上报 |

## 6. Evidence Graph

证据类型：TRANSACTION / ACCOUNT / CUSTOMER / RELATIONSHIP / TIMELINE / RULE / REGULATION / MODEL / ANALYST / COUNTER_EVIDENCE。

前端点击 Evidence 可回到原始交易、账户或法规摘录。

## 7. Bounded Challenger

输出结构化 JSON：`claim` / `predicate` / `args` / `evidence_ids` / `delta`。

越界、无证据、未知编号、跨案、未知谓词、谓词经数据核验不成立 → **Reject**。最终分 = 规则因子合计 + **通过校验**的 delta，夹紧到 [0, 1]。

## 8. Privacy & Security

- PrivacyMap：姓名 → `CLIENT_001`，账号 → `ACCOUNT_001`，仅 LLM 上下文脱敏，签发前受控还原。
- 工具白名单只读；禁止改交易/客户/规则、删数据、自动报送。
- CORS 默认只放行本地 Vite 源，可用 `HUICHA_CORS_ORIGINS` 覆盖；**不是** `allow_origins=["*"]`。
- `HUICHA_DEMO_TOKEN` 为空则接口开放；填写后需 `X-Huicha-Token`。这是竞赛原型口令，**不是银行登录/SSO**。
- 日志分级 INFO / WARNING / ERROR / AUDIT，账号类 token 脱敏。

## 9. Benchmark

- 机制验证：`cd backend && python -m app.experiments`（模板精标 + stub，**不是准确率**）。
- 能力指标框架：`python experiments/benchmark.py` → **Not evaluated yet**。
- 当前库约 80 条模板精标（`ALT-EXT-01`…）+ 路演案 A/B/C/D/F/L；`gold_label` 与规则模板同源。
- 独立测试集约 300–1000 条：TODO。

## 10. Demo

一键：`cd backend && python -m app.demo`（案例 L：A→B→C→D 短时多层转移，合成数据）。

工作台快捷键 1–5：案例 A/B/C/F/L。

## 11. Installation

```bash
cd huicha-aml/backend
python -m pip install -r requirements-dev.txt
cd ../frontend
npm install
```

复制 `backend/.env.example` → `.env`，填写百炼 `DASHSCOPE_API_KEY`。无密钥时可将 `HUICHA_LLM_STUB=1`，Challenger/Reporter 走内置 stub（不是百炼）。

## 12. Usage

```bash
cd huicha-aml/backend
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd huicha-aml/frontend
npm run dev
```

浏览器 http://127.0.0.1:5173 。改种子后删除 `backend/huicha.db` 再启动。

## 13. Project Structure

```
huicha-aml/
  backend/app/     API、编排、规则 Analyst、报告草稿、证据、风险、脱敏、种子
  backend/tests/   pytest
  frontend/src/    Case Workspace
  experiments/     benchmark / ablation / hallucination 等框架
```

调查流水线拆分：`agents.py` 只编排；取数在 `tools.py`；规则打底在 `analyst_rules.py`；Challenger 校验只走 `validator.py`；报告模板在 `report_draft.py`；落库在 `case_store.py`。

工作台「规则分」来自规则因子合计 + 通过校验的 delta，字段 `confidence_kind=rule_score_not_calibrated`。调分 Claim 的 `support_score` 在 `score_kind=predicate_verified` 时表示封闭谓词已在本案快照上执行为真，**不是语义置信度或校准概率**。无谓词的中性说明（delta=0）仍可为 `id_membership`。

## 14. Limitations

1. 数据全部为**合成数据**；模板精标与规则同源，不能写成准确率。
2. 竞赛/研究原型：SQLite 文件库，无银行 SSO，无生产级权限模型。
3. 知识库约十余条公开要求**转述**，检索是关键词重叠，不是向量检索。
4. LLM 输出必须人工审核；Agent 不得自动报送。
5. 实验结果只对当前机制验证/Benchmark 设置有效。
6. 能力指标（Accuracy 等）**Not evaluated yet**，未做真人对照效率实验。

## 15. Future Work

P0 独立合成测试集与 Evidence gold；P1 法规版本治理与权限模型；P2 调查效率真人对照。详见仓库改造说明。
