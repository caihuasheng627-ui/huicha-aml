# 慧查 AML V2.0

**AI 负责推理，规则负责边界，证据负责事实，人负责最终决策。**

面向金融机构**反洗钱告警后调查**的证据驱动、规则约束、可审计、Human-in-the-loop 调查 Copilot（竞赛/研究原型）。

## 1. Project Overview

上游检测已经产生告警。本系统不替代监测引擎，只把告警升级为**案件（Case）**：规划调查 → 收集证据 → 规则打底风险 → 有界质疑 → 校验 Claim → 结构化报告 → **人工签发**。

数据标记为 `synthetic`。不连接真实银行，不代表生产系统。

## 2. Business Problem

告警后调查耗时长、容易确认偏误、结论难回溯。需要把「AI 生成的判断」关在证据、规则、权限和审计之内，并由人做最终金融决策。

## 3. Core Innovation

1. **Evidence Graph**：Claim → Evidence → Source，禁止无证据结论。
2. **Bounded Challenger**：主动找反证；`delta` 必须 ∈ [−0.15, +0.15]，否则 Reject。
3. **Evidence Validator**：无证据 / 假证据 / 跨案证据不得进分。
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

输出结构化 JSON：`claim` / `counter_claim` / `evidence_ids` / `confidence` / `delta` / `reason`。

越界、无证据、未知编号、跨案 → **Reject**。最终分 = 规则因子合计 + **通过校验**的 delta，夹紧到 [0, 1]。

## 8. Privacy & Security

- PrivacyMap：姓名 → `CLIENT_001`，账号 → `ACCOUNT_001`，仅 LLM 上下文脱敏，签发前受控还原。
- 工具白名单只读；禁止改交易/客户/规则、删数据、自动报送。
- 日志分级 INFO / WARNING / ERROR / AUDIT，账号类 token 脱敏。

## 9. Benchmark

- 机制验证：`cd backend && python -m app.experiments`（模板精标 + stub，**不是准确率**）。
- 能力指标框架：`python experiments/benchmark.py` → **Not evaluated yet**。
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

复制 `backend/.env.example` → `.env`，填写百炼 `DASHSCOPE_API_KEY`。

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
  backend/app/     API、Agent、证据、风险、脱敏、种子
  backend/tests/   pytest
  frontend/src/    Case Workspace
  experiments/     benchmark / ablation / hallucination 等框架
```

## 14. Limitations

1. 数据主要为**合成数据**。
2. 属于研究/竞赛原型，**不代表真实银行生产系统**。
3. 法规知识库是公开要求**转述**，须持续维护，禁止当全文。
4. LLM 输出必须人工审核。
5. 实验结果只对当前机制验证/Benchmark 设置有效。
6. 能力指标（Accuracy 等）**Not evaluated yet**，未做真人对照效率实验。

## 15. Future Work

P0 独立合成测试集与 Evidence gold；P1 法规版本治理与权限模型；P2 调查效率真人对照。详见仓库改造说明。
