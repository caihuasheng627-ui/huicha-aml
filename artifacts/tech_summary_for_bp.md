# 循证慧查 · 商业计划技术事实源

**对应代码**：仓库默认分支 `main` HEAD `67317cd`（2026-09-20 已 `git fetch origin main` 对齐）。  
**产品对外名**：循证慧查。代码目录 / 环境变量仍为 `huicha-aml` / `HUICHA_*`。  
**作品类型**：可演示调查工作台原型 + 业务方案。  
**数据性质**：本地合成数据，不对接银行核心，不使用真实客户信息。  
**health 版本字段**：`3.0.1`（`backend/app/main.py`）；README 对外仍写 V3.0。

> **全篇口径**：下文只陈述代码里已经存在的机制。标「方案层 / 未实现」的不得写成已上线。实验数字只证明闸门或提示词标准能否闭合，**不是生产调查准确率，也不是人效**。`experiments/efficiency_records.csv` 目前只有表头，禁止写效率提升百分比。

---

## 1. 产品在反洗钱流水线中的位置

上游交易监测（规则或模型）已经产出告警。循证慧查**不替代监测引擎**，只覆盖监测之后、STR 正式报送之前的人力最密环节：

```
交易发生
  → 监测/检测（规则或模型，产出告警）     ← 灰色：上游已有系统，本作品不替代、不比 AUC
  → 告警池 → 调查取证 → 写底稿 → 双控签发  ← 蓝色：本作品覆盖
  → 可疑交易报告（STR）报送监测中心         ← 下游：本系统只出已签草稿，从不自动报送
```

**一句话定位**：把告警升级为案件（Case），由受控流水线只读取数、提取事实指标、脱敏后交 AI Judge 给出带证据编号的三档建议（排除 / 继续观察 / 建议上报）和四段调查底稿；调查员提交复核、合规复核岗签发后，得到的是**已签草稿**，状态不是「已报送」。

设计原则（可作副标题）：**AI 负责推理，规则负责边界，证据负责事实，人负责最终决策。**

服务对象：银行反洗钱调查岗（一级处置）与合规复核岗（二级签发）。后台工具，不面向客户。

**明确不做什么**

| 不做 | 代码依据 |
|------|----------|
| 不替代交易监测 / 不比检出率 | 告警由种子写入，`Alert.upstream` 默认为「规则引擎模拟告警」；无监测模型训练代码 |
| 不自动向监测中心报送 STR | `decide` 返回 `final_action: human_only`；无报送工具；`can_sign` 只放行人工签发 |
| 不连接真实核心 / 真实客户 | 全部 `data_note=synthetic`；SQLite 文件库 |
| 不把 AI 建议写成监管结论 | 三档只映射建议动作 CLOSE / MONITOR / REPORT_REVIEW，Agent 不得执行 |

赛道桥（可写，但不要写成已测效果）：洗钱资金常来自诈骗、赌博等上游犯罪；调查提效是为了更快固定证据、走完上报路径。仓库**没有**追赃时效实测。

---

## 2. 端到端案件流（告警 → 草稿 → 双控 → 已签草稿）

对应图：`huicha-aml/figures/fig_flow_biz.drawio`。接口：`backend/app/main.py`、岗位闸门：`backend/app/workflow.py`。

### 2.1 岗位与登录（竞赛原型，不是银行 SSO）

演示账号在 `backend/app/security.py`：

| 工号 | 界面岗位名 | `role` 字符串 | 口令 |
|------|------------|---------------|------|
| 002183 | 调查员 | `反洗钱调查员` | `aml123` |
| 002201 | 复核岗 | `合规复核` | `aml123` |

签发与导出始终需要会话头 `X-Huicha-Session`。`HUICHA_DEMO_TOKEN` 为空时**读接口开放**（演示配置）；填写后读请求还要 `X-Huicha-Token`。这不是 IAM / SSO / 岗位权限继承。

### 2.2 作业步骤

1. **接案**  
   调查员从待办领取一条告警（`GET /api/alerts`）。告警与案件 1:1。快捷键 `0` 锁定比赛主线案例 L（`ALT-L-20260910`）；`1`–`6` 打开 A/B/C/F/L/H（只打开，不重跑）。

2. **生成调查草稿**  
   `POST /api/alerts/{id}/investigate`，进度走 `GET .../investigate/stream`（SSE；失败回落 POST）。编排入口 `backend/app/agents.py` → `pipeline/runner.py`。工作台并排展示「规则对照 / AI Judge / 护栏后建议」，三者**不相加**。

3. **人在工作台审阅**  
   证据编号可点回流水 / 账户 / 法规摘录；看支持证据、反向证据、缺失材料、被拒绝的 Claim、事实回查问题、系统是否弃权。

4. **调查员提交复核**（`decision=submit`）  
   只能 `submit` 或 `reject`（退回重查），**不能自己签发**。`can_sign=false` 时须填写说明才能提交。提交后告警状态 `pending_review`，案件 `PENDING_REVIEW`。提交人不得复核本人。

5. **复核岗签发**  
   - `confirm`：同意签发。`can_sign=false` 时**禁止**。  
   - `modify`：修改后签发。`can_sign=false` 时必须写修改说明（有说明即可通过岗位闸，见下节「不要写过头」）。  
   - `reject`：退回调查。  
   签发后：排除 → 告警 `closed` / 案件 `CLOSED`；观察 → 告警 `monitoring` / 案件 `CLOSED`；建议上报 → 告警 `ready_to_file` / 案件仍为 `PENDING_REVIEW`。  
   **没有任何路径把状态写成已报送。** Schema 虽有字面量 `REPORTED`（`backend/app/schema.py`），`_case_status_after_decide` **从不返回它**。

6. **导出**  
   `GET /api/alerts/{id}/export` 输出 Markdown 四段底稿。文件头声明为调查底稿、非监测中心报文；写入导出人、签发状态、脱敏策略。签发后拒改草稿备注（`backend/app/notes.py` 的 `FINALIZED = {confirm, modify}`）。

### 2.3 三档建议（Agent 不得执行报送）

| 内部标签 | 界面文案 | 系统建议动作 | 人工作业要点 |
|----------|----------|--------------|--------------|
| `exclude` | 排除 | CLOSE（建议关闭） | 排除理由须留痕 |
| `observe` | 继续观察 | MONITOR（建议持续监测） | 须列 `missing_evidence` |
| `suggest_report` | 建议上报 | REPORT_REVIEW（建议进入上报复核） | 须人签；不是已报送 |

`confidence` 字段标记为 `confidence_kind=llm_self_assessed_not_calibrated`：模型自评把握度，**不是**校准概率、准确率或风险分数。

### 2.4 路演合成案（`gold_label` 由模板写入，不是专家盲标）

| 案例 | ID | 画像 | 告警类型 | 模板档 | 用途 |
|------|-----|------|----------|--------|------|
| A | `ALT-A-20260910` | 华东百货批发 | 大额频繁 | exclude | 经营合理性排除 |
| B | `ALT-B-20260910` | 自由职业个人 | 拆分存入后集中转出 | suggest_report | 贴线拆分 |
| C | `ALT-C-20260910` | 新设贸易代理 | 多账户资金归集 | suggest_report | 归集 |
| D | `ALT-D-20260909` | 退休、已登记亲属购房 | — | exclude | 填充 |
| E | `ALT-E-20260908` | 餐饮夜间 POS | — | exclude | 填充 |
| F | `ALT-F-20260910` | 退休、对手未登记 | 大额转账（未登记亲属） | observe | 证明有观察档 |
| L | `ALT-L-20260910` | 过桥账户（合成 Demo） | 短时多层转移 | suggest_report | **比赛主线** |
| H | `ALT-H-20260910` | 高量流水 | — | suggest_report | 「窗口约 150 笔 → 进模 ≤30 笔」 |

另有 `ALT-EXT-01`…约 80 条模板精标（`backend/app/seed_extended.py`），与规则分支同源，**不是独立人工标注集**。

---

## 3. 四层架构（接入 / 编排 / 治理 / 能力）

对应图：`huicha-aml/figures/fig_roadmap.drawio`。能力层只提供工具与存储，**不改变决策权**。

```
接入   上游告警 → 分岗待办 → 工作台（证据、三栏建议、签发栏）
编排   Planner → Collector → Privacy → Analyst → Judge → Skeptic → Reporter → Guardrail → Assemble
治理   证据契约 / 事实回查 / 政策护栏 / 弃权 / 双控签发 / 审计 / 禁止自动报送
能力   只读工具 · 知识库检索 · LLM 网关 · SQLite（案件与审计）
```

| 层 | 对评委说什么 | 主要代码 |
|----|--------------|----------|
| **接入** | 调查员领案、看证据、点编号回溯；复核岗只看待复核 | `frontend/src/App.jsx`、`workstation.js`、`CasePanels.jsx`、`Graph.jsx`；`GET /api/alerts`、`/api/auth/*` |
| **编排** | 九段显式 Stage，职责写在类上，不在一个 prompt 里混做 | `backend/app/agents.py`、`pipeline/runner.py`、`pipeline/stages/*` |
| **治理** | 闸门在代码里：假引用不可直接签发、幻觉账号标红、提交人不得签本人、无报送工具 | `workflow.py`、`decision.py`、`tools.fact_check`、`reliability.py`、`tool_audit.py`、`notes.py` |
| **能力** | 只读取数、本地法规检索、模型网关、文件库 | `tools.py`、`knowledge.py`、`llm.py`、`privacy.py`、`sampler.py`、`predicates.py`、`database.py` |

前端：React 18 + Vite 6 + Ant Design 5（`frontend/package.json`）。开发端口 5173，`/api` 代理到后端 8000。

---

## 4. 九段流水线：代码中的 role 名、职责、禁止、规则还是模型

**真实执行顺序**以 `STAGES` 为准（`backend/app/pipeline/stages/__init__.py`），不是计划书表 4 / `fig_pipeline.drawio` 里「护栏在成稿前」的画法：

```
Planner → Collector → Privacy → Analyst → Judge → Skeptic → Reporter → Guardrail → Assemble
```

Guardrail 必须在 Reporter **之后**，因为它要消费 Reporter 产出的 `fact_issues`。Privacy Stage 本身只建映射表，真正出站脱敏发生在 Judge/Reporter 调模型时（见第 6 节）。≤30 笔代表样本是 Analyst 调 `sampler.select_for_judge`，**不是** Collector 抽的。

| # | `name` / `role`（代码原名） | 做什么 | 禁止 | 规则还是 LLM |
|---|------------------------------|--------|------|--------------|
| 1 | `planner` / **Planner** | 按 `alert_type` 从白名单选本轮只读工具子集（`plan_tool_names`） | 不打分、不写报告、不报送；**不由模型决定调哪些工具** | **规则**（`planner_v2` 只记版本，不送模型） |
| 2 | `collector` / **Collector** | 按告警窗口取全量流水（默认前 90 天 + 后 7 天，`HUICHA_TX_WINDOW_DAYS`）；按计划调基线/图谱/名单/法规；关联账户少时并入一度对手流水 | 不编造交易或客户；不抽进模样本 | **规则** + 只读 SQL |
| 3 | `privacy` / **Privacy** | 从 bundle 登记姓名/账号/客户号，建成 `PrivacyMap` | 本段不把明文发给模型（发给模型发生在后续 LLM 调用） | **规则** |
| 4 | `analyst` / **Analyst** | `analyst_rules.analyze` 提取事实指标与规则分；`rule_baseline` 映射三档作**对照**；`select_for_judge` 抽 ≤30 笔代表样本 + 簇汇总；构图 | 不把上游告警标签直接计分定档；抽数不得交给模型 | **规则**（`SAMPLE_CAP=30`） |
| 5 | `judge` / **Judge** | 调 `enrich_judge`，输出结构化三档建议；`normalize_judge` + `verify_judge`（引用契约 + 可执行谓词）；失败则带问题重试一次，再降级为规则对照 | 不得引用进模样本/簇代表之外的编号；截断输出不写缓存 | **LLM**（产品 prompt=`judge_v3p`）；失败降级为规则 |
| 6 | `skeptic` / **Skeptic** | 从已通过契约的 Judge 抽出已核验主张；有界贪心删关键证据后**重跑 Judge**（最多 4 个候选、3 轮）；计算 `agent_reliability`（committed / abstain） | 不是第二个「质询大模型」；`skeptic_v1` 文案不送模型。反事实轮次无效则倾向档不得直接签发 | **规则编排** + 反事实轮次再调 **LLM Judge** |
| 7 | `reporter` / **Reporter** | 先渲染确定性四段模板；Judge 契约通过且未弃权时用 `enrich_full_report` 生成全文；事实问题定向再调一次；可选注入幻觉账号 `6222-FAKE-9999` 供演示 | 不自动上报；弃权时改用弃权语气、不调全文模型 | 模板 **规则**；润色 **LLM**（`reporter_v3`） |
| 8 | `guardrail` / **PolicyGuardrail** | `apply_guardrails`：任何建议须人签；名单命中不得直接排除（最低升为观察）；事实回查**硬问题**阻断签发 | 不与 AI 分加权；只否决或升级 | **规则** |
| 9 | `assemble` / **Assemble** | 组装 payload、`can_sign`、`sign_blockers`、落库、审计 | 不报送；不跳过双控 | **规则** |

工具白名单（全部只读，`backend/app/tools.py` `ALLOWED_TOOLS`）：

`get_alert`、`get_customer`、`get_accounts`、`get_transactions`、`get_related_accounts`、`get_network`、`get_graph`、`get_timeline`、`get_baseline`、`check_watchlist`、`search_knowledge`、`search_regulation`。

Planner 按告警类型加减：大额/频繁/夜间/转账会加基线与图谱；拆分/归集/名单/团伙会加关联账户与关注名单。每次 `@tool` 调用写入 `tool_trace` 与 `AuditLog`（`tool_audit.py`）。**没有**写核心、删库、报送工具。

**可选、默认关闭**：`HUICHA_JUDGE_TOOLS=1` 时 Judge 可在白名单内最多两轮只读补证（`pipeline/toolkit.py`）。竞赛演示与现网产品路径应保持默认关。

关闭慧查 agent（`use_challenger=false`，实验/对照模式）：不调 Judge/Reporter 模型，只展示规则对照与模板骨架；界面会标明「慧查agent 已关闭」。评委若问「去掉大模型还能用吗」：**能降级查账和看对照，但没有证据综合建议、缺失材料研判和 AI 全文草稿**。

---

## 5. 证据契约、事实回查、Skeptic/反事实、护栏 —— 代码里实际怎么做

### 5.1 证据图

构图器 `backend/app/evidence.py` 从工具结果生成节点，**禁止 LLM 创造节点**。主路径实际类型：

- `CUSTOMER` / `ACCOUNT` / `TRANSACTION` / `RELATIONSHIP` / `REGULATION`
- Judge 每条理由追加 `MODEL`（`reporter.py`）

Schema 还列了 `TIMELINE` / `RULE` / `ANALYST` / `COUNTER_EVIDENCE`（`schema.py`），**主路径构图器不会生成这些类型**。不要按类型清单逐项念。

前端点 Evidence 回到 `source_id`（交易号、客户号、`KB-*`）。旧字段 `support_score` 若出现，`score_kind` 现为 `id_membership` 或 `predicate_verified`，**不是语义相似度**。

### 5.2 Evidence Judge 契约（产品默认 `judge_v3p`）

输出 JSON（`JudgeDecision`）：

`disposition` / `confidence` / `typologies` / `supporting_evidence_ids` / `contradicting_evidence_ids` / `missing_evidence` / `rationale[]`（`text` + `evidence_ids`，交易模式理由另含 `predicate` + `args`）/ `next_actions`。

`verify_judge`（`decision.py`，在 **Judge 段**执行，不在 Skeptic 段）硬否整份建议的情形包括：

- 理由为空、无引用、引用不在允许集合（进模样本或簇代表）
- 缺少结构化理由
- `suggest_report` 但无支持证据

另有可执行谓词（`backend/app/predicates.py` 封闭集合，例如 `amount_monotonic_decreasing`、`consecutive_transfer_chain`、`night_transfer`、`amount_near_threshold`…）：后端在本案交易快照上**重新执行**，不成立则记 `predicate_failed`。缺谓词时，系统会尝试从快照补一条为真的谓词；已有核验主张时，旁路失败行不再一票否决整份（2026-09 合入的契约放宽，见 `verify_judge` 注释）。

`missing_evidence` 若被模型写成编号，会被 `sanitize_missing_evidence` 丢掉，只保留中文材料名。

LLM 截断或非 JSON：先带 `repair_issues` 重试一次，再降级规则对照；截断输出不写缓存。

**三档可操作标准**（写在 `judge_v3` / `judge_v3p` prompt 里，不是另训练一个分类器）：

- **exclude**：来源与去向均有完整合理解释，干扰点已解释；材料足以闭合时不得因「可再补材料」降为观察。
- **observe**：无清晰异常节奏，但缺闭合资金链的关键材料；必须列出待补材料。
- **suggest_report**：有异常节奏且无经营/生活解释；**不得因材料不全降为观察**。

`judge_v4` **仅用于实验消融**，`prompt_version("judge")` 返回的是 **`judge_v3p`**，不要把 0.994 说成「当前产品 prompt 的成绩」。

### 5.3 事实回查

`tools.fact_check`：对报告全文正则抽取交易号、账号（含 `6222-`）、金额、日期、知识库编号等，与本轮工具 JSON 事实表比对。工具结果里没有的具体账号/编号 → `severity=hard`。  
「约 5 万元阈值」「月度流入约 200 万量级」等带阈值/同业/概数措辞的金额按语境放行（`LEXICON_WORDS`），避免误杀合规表述。

`hard_fact_issues` 只取硬问题，进入 Guardrail 与 `can_sign`。工作台「幻觉演示」会故意写入 `6222-FAKE-9999`，用于现场证明拦截，**不是生产中会主动造假**。

### 5.4 Skeptic / 反事实 / 弃权

`evidence_sufficiency.py`：有界贪心，**不宣称数学全局最小**。移除模型声称的关键支持证据簇后重跑 Judge。

| 反事实结果 | 含义 |
|------------|------|
| `faithful=true` | 去掉该证据后结论变了 → 说明建议依赖该证据 |
| `faithful=false` | 去掉后结论不变 → 标记供人工复核 |
| `faithful=null` | 反事实轮次未通过引用校验，**不判定为「建议未变化」** |

`reliability.py`：不改三档倾向，只决定 `stance`。硬原因（契约失败、谓词失败、Judge 降级、反事实输出无效且无证据核心）→ 弃权，不可直接签发。软原因（规则与 AI 分歧且把握度 &lt; 0.55、上报但未形成对声明证据的依赖）也弃权。弃权后倾向档仍显示，Reporter 改用弃权语气。

**不要写成**：「第二个大模型在质询 Judge」。Skeptic 是确定性校验 + 去证据重跑同一 Judge。

### 5.5 政策护栏与 `can_sign`

`apply_guardrails` 固定三条政策（不加权）：

1. 任何建议均须人工签发（禁止自动报送）
2. 关注名单命中且模型给 exclude → 升为 observe
3. 事实回查硬问题 → 阻断签发

`Assemble.can_sign` 为真当且仅当：无事实硬问题 **且**（未开 agent 或 Judge 契约通过）**且**（未开 agent 或 reliability 为 committed）。

岗位闸门比「Assemble 一票否决」更细，计划书不要写成「未过闸就完全不能动笔」：

- 调查员：`can_sign=false` 时**可以**带说明提交复核或写入备注。  
- 复核岗：`confirm` 在 `can_sign=false` 时禁止；`modify` 只要有修改说明即可签发。  
- 签发后不能再改备注。

这是「人可以在写明理由后覆盖系统建议」，不是「系统自动报送」。

---

## 6. 隐私 / 脱敏路径（明文 vs 出站）

策略版本 `privacy_v2`（`backend/app/privacy.py`）。

| 位置 | 是否明文 | 说明 |
|------|----------|------|
| 工作台、签发稿、SQLite `investigations.payload_json` | **受控明文** | 调查员要对姓名、账号、流水。库文件**不加密**，不是银行级存储 |
| 发给 LLM 的 messages | **占位符** | `prepare_for_llm`：姓名→`CLIENT_00n`，账号→`ACCOUNT_00n`，客户号→`CUST_00n`；然后 `assert_clean`，漏则中止调查 |
| 渠道聚合名 `CASH-` / `POS-` / `RELATIVE-` / `UNK-` | 保留语义 | 不发真实对手户名 |
| 交易号 `TX-*`、告警号、证据号、已是占位符的 token | 保留 | 供引用校验 |
| `city` / `phone` / `id_number` 等准标识 | **丢弃** | 不进模 |
| `chat()` HTTP 出站前门 | 再拦一次 | 未脱敏的 `6222-` 形态直接 `PrivacyLeakError` |
| LLM 缓存键 | 脱敏后上下文的 SHA-256 | 不缓存明文；截断/修复轮不写缓存 |

**生产方案（方案层，原型未做）**：数据不出域，或切换行内私有化模型。不要把当前 SQLite 文件库说成已加密、已不出域。

日志会对账号 token 与「××公司」形态脱敏。CORS 默认只放行本地 Vite 源，**不是** `allow_origins=["*"]`。

---

## 7. 技术栈与诚实原型边界

| 层 | 现状（可写进报告） | 不要写成 |
|----|--------------------|----------|
| 后端 | Python 3.12，FastAPI 0.115，SQLAlchemy 2.0，Pydantic 2.10，uvicorn 本机 `:8000` | 已容器化多活 / 生产网关 |
| 库 | SQLite 文件 `backend/huicha.db`；可用 `HUICHA_DATABASE_URL` 换引擎 | 已上 PostgreSQL 集群（**方案层**） |
| 前端 | React 18.3 + Vite 6 + Ant Design 5，`:5173` | 企业门户 / 行内统一认证套件 |
| 模型网关 | `llm.py` 标准库 `urllib` 调 OpenAI 兼容 Chat Completions。优先级：官方 DeepSeek 密钥 → 智谱 → 阿里云百炼。默认模型名见 `.env.example`：`DASHSCOPE_MODEL=deepseek-v4-flash-0731`。可用 `HUICHA_MODEL_JUDGE` / `HUICHA_MODEL_REPORTER` 分角色覆盖。无密钥设 `HUICHA_LLM_STUB=1` | 自研金融大模型 / 已行内私有化训练 |
| 知识库 | 作业口径 16 篇（`PLAYBOOK`）+ 法规章节（反洗钱法 7 章、CDD 5、UBO 5、大额可疑+监管办法 5，合计目录约 38 篇）。检索：关键词重叠 + 字符二元组 TF-IDF 余弦（`hybrid-keyword-tfidf`），按条切块。**不是**向量库 / 企业级 RAG | 「已内置现行有效法规全文库并实时更新」 |
| 登录 | 两套演示工号 + 口令 `aml123` | 银行 SSO |
| 测试 / CI | 后端 `test_*.py` **24** 个；前端脚本测试 **7** 个（`package.json` 的 `npm test`）；GitHub Actions：Python 3.12 pytest + Node 20 测试与构建（`.github/workflows/ci.yml`） | 生产渗透测试 |
| 数据 | 合成客户/账户/交易/告警/关注名单 | 已接核心 / AMLSim 生产流水 |

知识库四类：监管要素、调查类型学、行业基线、作业规程。playbook `KB-PROC-01` 仍写旧词「Challenger 必须尝试经营抗辩」，与现网「慧查 agent」不完全同名，引用时不要把 Challenger 说成仍在调分。

历史遗留（不要写进「当前判断公式」）：`risk.aggregate` 仍描述「规则因子 + Challenger delta」，但 Assemble 的 `scoring.mode` 已是 `judge_not_additive`，`llm_delta` 固定 0。最终建议来自过契约的 Judge + 护栏，规则分只对照。

---

## 8. `experiments/` 里两类实验：机制 vs 消融

必须分开写，禁止揉成一个「准确率」。

### 8.1 机制验证（闸门能不能复现）

- 命令：`cd huicha-aml/backend && python -m app.experiments`  
- 路径：跑**完整九段流水线**，但 Judge 被换成确定性 stub（`_offline_stub_chat`）。精标 `gold_label` 与生成模板同源。  
- 写入：`experiments/RESULTS.md` 的 A 节口径（注意：该命令会按 stub 模板**重写** RESULTS.md，真实模型表是后来手工保存在同一文件里的）。

| 指标 | 现文件中的结果 | 正确读法 | 禁止读法 |
|------|----------------|----------|----------|
| 事实回查拦截率（毒化草稿 n=200） | 100% | 测正则回查，**不经大模型** | 「大模型幻觉率 0」 |
| 干净文本误报率（n=200） | 0% | 阈值/概数措辞不被误杀 | 「已达生产级 NLP」 |
| Judge↔规则分歧率 | 40.2%（stub，n=87） | 证明两路不再加权 | 「AI 更准」 |
| 引用契约通过率 | 100%（stub） | 编号属于本案 | 「语义完全正确」 |
| 关键证据反事实覆盖率 | 59.8% | 有支持证据时才跑反事实 | 「模型准确率」 |
| 与模板 gold 档位重合 | stub 流程可到 100% | **由构造保证** | 「准确率 100%」 |
| 幻觉演示账号拦截 | 通过 | 工作台开关可复现 | — |

`experiments/ablation.py`、`hallucination.py`、`challenger.py` 等是**框架槽位**，能力指标常为 `Not evaluated yet`，不要当已测结果引用。

### 8.2 独立合成集上的真实模型消融（提示词标准能不能分开三档）

- 命令：`python experiments/benchmark.py`（`--real`、`--prompt judge_v2|judge_v3|judge_v4`）  
- 路径：**不是**完整九段。直调 `enrich_judge(db=None)` → `normalize_judge` → `verify_judge` → `apply_guardrails`。不跑 Privacy 工作台路径、不跑 Reporter 全文、不跑双控。  
- 数据：脚本生成的合成 vignette，金标按叙事族写入，**不是人工专家标注**。  
- 模型：报告中的主数字来自百炼 `deepseek-v4-flash-0731`。

**可以对外讲的对照（必须带数据集名和 prompt 名）**

1. **开发集 v3**（`independent_set.json`，n=240，11 族，`narrative_vignette_v3_rules_layer`）  
   同一模型、同一后处理，只换 prompt：`judge_v2` Macro-F1 **0.3867** → `judge_v3` **0.9662**。  
   含义：把三档可操作标准写进契约后，「默认观察」塌缩被拉开。  
   限制：v3 标准例举的异常节奏与该集上报族高度重合，0.97 是**条件乐观估计**（见 `REAL_MODEL_REPORT.md` §0、§7）。

2. **盲区 hold-out**（`blind_set.json`，n=220，例举词禁用）  
   `judge_v2` **0.4259** → `judge_v3` **0.9286**。keyword 基线掉到约 0.11。  
   含义：不完全是背例举词。仍是合成集。

3. **盲区 + `judge_v4`**（同一 `blind_set`）  
   Macro-F1 **0.994**（计分 215/220，parse_failures=5）：混淆矩阵 exclude 80/80、observe 39/39、suggest_report 95/96（1 条观察→上报，偏严）。verify 通过率 1.0；证据支持侧 P/R 0.777/0.967（只在叙事项 `IX-` 上算）。always_report 基线约 0.21。  
   **这是实验 prompt `judge_v4`，不是产品默认 `judge_v3p`。**

4. 去极性、结构盲区等有效性表见 `RESULTS.md`「有效性消融」。结构盲区上换官方 `deepseek-chat` 时 Macro-F1 约 0.87，说明**换模型会掉**，更不能外推生产。

**v1/v2 数据集已降级**（标签泄漏），不得与 v3 混比。

### 8.3 人效 / 专家盲标 —— 未完成

协议：`experiments/HUMAN_STUDY.md`。记录表为空。`gold_review_labels.json` 是实验作者自洽，**不得写成外部专家一致率**。真实脱敏 hold-out 接口占位：`experiments/benchmark/real_holdout.json`。

现场优先指屏幕：本次工具调用次数、四段要素是否非空、编号能否点回、幻觉账号是否标红且不可直接同意签发。实验室大表不要当准确率念。评委若问「97% / 99.4% 是不是准确率」：**不是，是合成集上的对照，须人工签发。**

---

## 9. 和监测产品 / 通用大模型包装 / 智盾链式检测 —— 我们不争什么

| 对照对象 | 他们争什么 | 循证慧查做什么 | 我们明确不争 |
|----------|------------|----------------|--------------|
| 规则/模型监测（含同赛道检测作品） | 检出、降误报、AUC | 接受已有告警，做调查与报告 | 不比「疑不疑」、不比 AUC |
| 智盾链类监测叙事 | 「这笔像不像洗钱」 | 「为什么、证据在哪、报告怎么写」 | 上下游互补，不是替代品 |
| 通用大模型直接写结论 | 生成流畅 | 只读工具 + 引用契约 + 谓词回放 + 反事实 + 护栏 + 双控人签 | 不拼无闸门裸生成 |
| 传统调查手册 | 人查人写 | 同一套监管要素，Agent 填初稿、人审定 | 不宣称替代调查员担责 |
| 规则引擎「智能调查」 | 规则打分定结论 | 规则只做对照与硬边界，判断由过契约的 AI 给出 | 不把规则分说成最终结论 |

可复述的四句（与 v4.1「项目特点」对齐，且与代码一致）：

1. **卡位**：监测之后的调查 Copilot。  
2. **分工**：AI 推理、规则定边界、证据定事实、人签最终决策；规则与 AI 不加权。  
3. **闸门可 Demo**：假引用不可直接同意签发、幻觉账号标红、反事实、双控、只读白名单 + 出站脱敏。  
4. **验证边界**：机制/消融数字只证明闸门与三档可分，不是生产准确率；人效百分比先不写。

---

## 10. 方案层 / 未实现（写进计划必须标明）

| 项 | 状态 |
|----|------|
| 只读对接行内告警队列、客户/交易查询服务 | 方案，未做 |
| 行内私有化模型 / 智能算力网关 | 可配置替换的接口已有；行内部署未做 |
| PostgreSQL 集群、容器多活 | 未做 |
| 银行 SSO / 生产权限模型 | 未做（仅演示工号） |
| 与 STR 填报系统草稿回填 | 方案，未做；即便做了仍须人点报送 |
| 法规版本治理（规章修订自动入库） | 未做 |
| Judge 工具补证（`HUICHA_JUDGE_TOOLS`） | 代码有，**默认关** |
| 教室人效对照、外部专家盲评、真实脱敏 hold-out | 协议有，记录空 |
| 在线用签发反馈再训练模型 | 反馈只入库统计（`/api/feedback`），**不承诺**再训练 |
| `schema.CaseStatus.REPORTED` | 仅类型字面量，签发路径不用 |

落地阻力相对较小的技术理由（可写）：不改监测引擎、不碰核心写权限、以 Copilot 嵌入「告警池 → 调查 → 报送」中间段。计费锚点技术侧只能承诺「按签发案件出草稿」，不要按检出条数与监测抢预算。

---

## 11. 给非工程评委的最短复述

上游监测已经喊「这笔可疑」。循证慧查不负责再喊一遍，而负责帮调查员把「为什么可疑、证据在哪、报告怎么写」写成一份能点回原流水的底稿。模型只能看见脱敏后的代表样本；每一句理由都要带本案证据编号，编号对不上或虚构账号出现在稿子里，复核岗就不能直接点「同意签发」。调查员提交、复核岗签发，系统永远不会替银行向监测中心报送。演示用的是合成客户和 SQLite，实验数字只说明这套闸门和三档标准能跑通，不能当成已经在生产里查准了。

---

## 12. 工程师核对索引

| 主张 | 文件 |
|------|------|
| 九段顺序 | `huicha-aml/backend/app/pipeline/stages/__init__.py` |
| 编排入口 | `backend/app/agents.py`、`pipeline/runner.py` |
| 工具白名单与窗口 | `backend/app/tools.py` |
| 抽数上限 30 | `backend/app/sampler.py` `SAMPLE_CAP` |
| 规则对照 | `backend/app/analyst_rules.py`、`decision.rule_baseline` |
| Judge 契约 / 护栏 | `backend/app/decision.py` |
| 产品 prompt | `backend/app/prompts.py` `prompt_version("judge")` → `judge_v3p` |
| 谓词 | `backend/app/predicates.py` |
| 反事实 | `backend/app/evidence_sufficiency.py`、`pipeline/stages/skeptic.py` |
| 弃权 | `backend/app/reliability.py` |
| 事实回查 | `backend/app/tools.py` `fact_check` / `hard_fact_issues` |
| 脱敏 | `backend/app/privacy.py`、`llm.py` `inspect_outbound` |
| 双控 | `backend/app/workflow.py`、`main.py` `decide` |
| 登录 | `backend/app/security.py` |
| 四段底稿 | `backend/app/report_draft.py` |
| 知识库 | `backend/app/knowledge.py` + `knowledge_*.py` |
| 机制实验 | `backend/app/experiments.py` |
| 真实模型消融 | `experiments/benchmark.py`、`RESULTS.md`、`REAL_MODEL_REPORT.md` |
| 人效空表 | `experiments/HUMAN_STUDY.md`、`efficiency_records.csv` |
| CI | `.github/workflows/ci.yml` |
