# 循证慧查 V3.0

**AI 负责推理，规则负责边界，证据负责事实，人负责最终决策。**

对外名称：**循证慧查**。代码目录与环境变量仍为 `huicha-aml` / `HUICHA_*`（历史路径，产品名以循证慧查为准）。

面向金融机构**反洗钱告警后调查**的证据驱动、规则约束、可审计、Human-in-the-loop 调查 Copilot（竞赛/研究原型）。

对外技术说明（供商业计划最终报告）：仓库根目录 `循证慧查-技术文档（供商业计划最终报告）.md`。  
工行杯项目计划书初版：仓库根目录 `循证慧查-项目计划书（初版）.md`。  
答辩口径、禁语与红队 20 题：仓库根目录 `答辩作战手册.md`。  
比赛主线：`比赛演示脚本-3分钟.md`（快捷键 `0`）。

## 1. Project Overview

上游检测已经产生告警。本系统不替代监测引擎，只把告警升级为**案件（Case）**：规划调查 → 收集证据 → 事实指标 → AI Judge 完整建议 → Skeptic 核验/反事实 → 政策护栏 → 全文报告 → **人工签发**。

V3 不再把上游告警类型重复计入规则分，也不再用“规则分 + LLM delta”合成结论。AI Judge 在证据约束下直接输出三档调查建议；规则只做独立对照和不可绕过的政策边界。Collector 按告警窗口取全量流水，确定性规则抽出代表样本；基线合计来自窗口全量，模型只见样本。

数据标记为 `synthetic`。不连接真实银行，不代表生产系统。

## 2. Business Problem

告警后调查耗时长、容易确认偏误、结论难回溯。需要把「AI 生成的判断」关在证据、规则、权限和审计之内，并由人做最终金融决策。

## 3. Core Innovation

1. **Evidence Graph**：Claim → Evidence → Source，禁止无证据结论。
2. **Evidence Judge**：直接输出 `exclude / observe / suggest_report`、支持证据、反向证据、缺失材料、逐条理由和下一步动作。
3. **Skeptic + Counterfactual**：伪造引用、无引用理由会使整份建议失效；移除模型声称的关键证据后重跑，检查结论是否连贯变化。
4. **Policy Guardrail**：名单命中不得直接排除、事实回查失败不得签发；护栏只否决或升级，不与模型加权。
5. **Full-report Reporter**：生成完整四段调查底稿，事实不一致时定向修复一次。
6. **Human-in-the-loop**：Agent 只能建议进入 `REPORT_REVIEW`，不能执行报送。

## 4. System Architecture

```
Transaction / Customer / Account / Relationship
        ↓
Case → Planner → Evidence Collector → Indicator Analyst
        → Privacy Gate → Evidence Judge → Skeptic / Counterfactual
        → Policy Guardrail → Full-report Reporter
        → Human Approval → Audit Trail
```

## 5. Agent Architecture

| 角色 | 职责 | 禁止 |
| --- | --- | --- |
| Planner | 只规划白名单只读工具 | 不打分、不报送 |
| Collector | 只读取数，写入 Evidence；按告警窗口取全量流水，再用确定性规则抽代表样本。Judge 引用必须落在进模样本或簇代表 | 不编造事实；**不得由模型决定抽哪笔** |
| Analyst | 从流水/KYC/图谱计算事实指标和规则对照 | 不读取告警标签给结论加分 |
| Privacy | 进模前把姓名/账号/客户号换成占位符，出站检漏 | 不得把明文 PII 发给模型 |
| Judge | 输出完整建议、支持/反向/缺失证据及行动 | 不得引用工具范围外事实 |
| Skeptic | 校验逐条引用并做关键证据反事实 | 失败建议不得签发 |
| Policy Guardrail | 执行名单、事实完整性等硬边界 | 不与 AI 评分合成 |
| Reporter | 基于已校验建议生成完整四段草稿 | 不自动上报 |

## 6. Evidence Graph

证据类型：TRANSACTION / ACCOUNT / CUSTOMER / RELATIONSHIP / TIMELINE / RULE / REGULATION / MODEL / ANALYST / COUNTER_EVIDENCE。

前端点击 Evidence 可回到原始交易、账户或法规摘录。

## 7. Evidence Judge Contract

输出结构化 JSON：`disposition` / `confidence` / `typologies` / `supporting_evidence_ids` / `contradicting_evidence_ids` / `missing_evidence` / `rationale[]` / `next_actions`。

每条 `rationale` 必须引用本轮工具返回的证据编号。未知编号、无引用理由、建议上报但无支持证据 → 整份建议校验失败并阻断签发。`confidence` 只是模型自评把握度，不是校准概率。

当前 Judge prompt 为 `judge_v3`：在 `judge_v2` 的引用契约之上写明三档可操作判定标准——来源与去向均有完整合理解释且干扰点已解释 → `exclude`；无清晰异常节奏但缺关键材料 → `observe`（必须列 `missing_evidence`）；异常节奏（短时多点取现回流、当日多层递减过桥、关联对倒闭环、现金→兑换商、分散归集→集中外转）且无经营/生活解释 → `suggest_report`（不因材料不全降档）。另要求 `missing_evidence` 为空时不得给 `observe`、每条理由写明推向哪一档、`confidence` 随证据强弱变化。消融对比见 `experiments/REAL_MODEL_REPORT.md`。

真实百炼调用中已处理的模型行为（`judge_v2` 起沿用）：

- 输出被 `max_tokens` 截断或非 JSON：先带针对性提示重试一次，再降级到规则对照；截断输出不写缓存。
- `missing_evidence` 被填成证据编号/编号区间：自动剔除并记录到 `sanitized_missing_evidence`，只保留材料描述。
- 反事实轮次：其余指标中同步剔除已移除证据；该轮输出未通过引用校验时 `faithful=null`，不判定为「建议未变化」。
- 报告回查把 `ALT-`/`EV-` 编号当作整体 token，并把本案告警号、全部合法证据号纳入已知引用，避免把编号里的日期片段误报。

## 8. Privacy & Security

- Privacy 层（`privacy_v2`）：工作台与签发稿保持受控明文；**只有 LLM 出站**走脱敏。
- PrivacyMap：姓名 → `CLIENT_001`，账号 → `ACCOUNT_001`，客户号 → `CUST_001`；渠道聚合名 `CASH-`/`POS-`/`RELATIVE-` 保留语义。交易编号 `TX-*` 不替换，供引用校验。
- `prepare_for_llm`：字段级替换后 `assert_clean`；`city`/`phone`/`id_number` 等准标识直接丢弃。命中未脱敏字段则中止调查。
- `chat()` 出站前门再拦截 `6222-` 账号形态；LLM 缓存 hash 的是脱敏后上下文。
- 调查 payload 带 `privacy` 凭证（登记数量、出站次数）；工作台展示「进模脱敏」标签。
- 工具白名单只读；禁止改交易/客户/规则、删数据、自动报送。
- CORS 默认只放行本地 Vite 源，可用 `HUICHA_CORS_ORIGINS` 覆盖；**不是** `allow_origins=["*"]`。
- `HUICHA_DEMO_TOKEN` 为空则读接口开放；填写后需 `X-Huicha-Token`。签发与导出始终需要演示登录会话。这是竞赛原型口令，**不是银行登录/SSO**。
- 日志分级 INFO / WARNING / ERROR / AUDIT；账号 token 与「××公司」形态会脱敏，作业中文不整段抹掉。
- SQLite 调查载荷仍为明文，**不是**银行级加密或数据不出域。

## 9. Benchmark

- 机制验证：`cd backend && python -m app.experiments`（模板精标 + stub，**不是准确率**）。
- 能力指标框架：`python experiments/benchmark.py`（框架状态与离线基线）；`--real` 在独立合成集上真实调用产品 Judge，`--prompt judge_v2` 做消融。
- 当前库约 80 条模板精标（`ALT-EXT-01`…）+ 路演案 A/B/C/D/F/L；`gold_label` 与规则模板同源。
- 独立合成集 v3：240 条唯一输入、11 个叙事族、规则层同构、无标签泄漏（`experiments/benchmark/independent_set.json`）。真实模型消融（同一集，唯一变量 prompt）：`judge_v2` Macro-F1 0.39 → `judge_v3` 0.97；**合成集实验对照，不是生产准确率**，读数与限制见 `experiments/REAL_MODEL_REPORT.md`。
- 人工标注的真实脱敏 hold-out：TODO。

## 10. Demo

工作台快捷键 `0`：比赛演示（锁定案例 L 主线）。`1`–`6`：案例 A/B/C/F/L/H（只打开，不重跑）。案例 H 用于演示「窗口约 150 笔 → 进模 ≤30 笔」。

一键后台冒烟：`cd backend && python -m app.demo`（stub，不要当成现场真实模型输出）。

比赛现场 3 分钟：见 [比赛演示脚本-3分钟.md](比赛演示脚本-3分钟.md)。口播与禁语见仓库根目录 `答辩作战手册.md`。

## 11. Installation

```bash
cd huicha-aml/backend
python -m pip install -r requirements-dev.txt
cd ../frontend
npm install
```

复制 `backend/.env.example` → `.env`，填写百炼 `DASHSCOPE_API_KEY`，或 `DEEPSEEK_API_KEY` / `ZHIPU_API_KEY`。无密钥时可将 `HUICHA_LLM_STUB=1`，Judge/Reporter 走内置 stub。

## 12. Usage

```bash
cd huicha-aml/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
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

调查流水线：`agents.py` 门面；`pipeline/` 显式 Stage（Planner → Collector → Privacy → Analyst → Judge → Skeptic → Reporter → Guardrail → Assemble）；`tools.py` 取数；`analyst_rules.py` 提取指标；`decision.py` 负责 Judge 契约、规则对照与政策护栏；`llm.py` 统一 `call_json`/`call_text` 调用 Judge/Reporter；`report_draft.py` 提供降级模板；`case_store.py` 落库。

可选环境变量：`HUICHA_MODEL_JUDGE` / `HUICHA_MODEL_REPORTER` 按角色覆盖模型；`HUICHA_JUDGE_TOOLS=1` 允许 Judge 在白名单内最多两轮只读补证（默认关）。调查进度可通过 `GET /api/alerts/{id}/investigate/stream` 以 SSE 推送阶段事件；工作台优先走流式并在失败时回落 POST。

工作台并排展示“规则对照 / AI Judge / 护栏后建议”。两者**不相加**。字段 `confidence_kind=llm_self_assessed_not_calibrated` 明确模型把握度未经校准。

## 14. Limitations

1. 数据全部为**合成数据**；模板精标与规则同源，不能写成准确率。
2. 竞赛/研究原型：SQLite 文件库，无银行 SSO，无生产级权限模型。
3. 知识库含 **2024 年修订《反洗钱法》全文**（按章目录、按条检索）及 2025 年配套规章官方条款，另有作业口径转述；检索为**关键词重叠 + 字符二元组 TF-IDF 余弦**混合，不是向量数据库。
4. LLM 输出必须人工审核；Agent 不得自动报送。
5. 实验结果只对当前机制验证/Benchmark 设置有效。
6. 独立合成集上已跑产品 Judge 消融，**禁止**写成生产准确率；人效对照未完成，禁止填写提升百分比。见 `experiments/HUMAN_STUDY.md`。

## 15. Future Work

P0 教室人效对照与外部盲评（`experiments/HUMAN_STUDY.md`）；P1 法规版本治理与权限模型；P2 只读对接告警队列。合成集与 Evidence 协议已在 `experiments/`。详见 `答辩作战手册.md`。
