# 循证慧查 技术栈总报告

对外名称：循证慧查  
版本：V2.1（竞赛/研究原型）  
代码：`huicha-aml/`（环境变量仍为 `HUICHA_*`）  
口径：只写当前仓库已落地的选型，不写成生产系统。

---

## 1. 一句话

本地 **B/S 调查工作台**：Python FastAPI 编排多智能体流水线，React 出案件视图；数据在 SQLite 合成库，大模型只做有界质疑与报告润色，规则与校验器决定分数边界。

```
浏览器 (Vite :5173)
    │  /api 代理
后端 FastAPI (:8000)
    ├─ SQLAlchemy → SQLite (huicha.db)
    ├─ 规则 Analyst / Validator / 证据图（本地逻辑）
    └─ 百炼 Chat Completions（可选 stub）
```

---

## 2. 分层选型

| 层 | 选型 | 现状 |
|----|------|------|
| 前端 | React 18、Vite 6、Ant Design 5 | JS（无 TypeScript）；开发端口 5173 |
| 后端 | Python 3.12、FastAPI 0.115、Uvicorn 0.34 | 端口 8000；Pydantic 2 做接口模型 |
| ORM / 库 | SQLAlchemy 2.0、SQLite 文件库 | `backend/huicha.db`；可用 `HUICHA_DATABASE_URL` 覆盖；**无** Docker / PostgreSQL |
| 大模型 | 阿里云百炼兼容 OpenAI 的 Chat Completions | 标准库 `urllib` 直调，**未**引入 OpenAI SDK；默认模型 `deepseek-v4-flash-0731` |
| 知识库 | 内存文档 + 关键词重叠 top-k | 约 16 条公开要求转述；**不是**向量检索 / RAG |
| 测试 | pytest 8、httpx | `backend/tests/` |
| CI | GitHub Actions | Python 3.12 跑测试 + Node 20 构建前端 |

依赖清单：`huicha-aml/backend/requirements.txt`、`huicha-aml/frontend/package.json`。

---

## 3. 运行时怎么拼

| 环节 | 实现 | 不依赖 |
|------|------|--------|
| 调查编排 | `agents.py`：Planner → Collector → Analyst → Challenger → Validator → Aggregator → Reporter | 无 LangChain / AutoGen |
| 取数 | `tools.py` 白名单只读工具 | 无银行核心、无外部数据源 |
| 打底分 | `analyst_rules.py` 规则因子 + 先验 | 不经 LLM |
| 质疑 | 百炼 JSON（`claim` / `predicate` / `delta`）或 `HUICHA_LLM_STUB=1` | delta 越界即 Reject |
| 校验 | `validator.py` + 封闭谓词在本案快照上重放 | 无语义相似度模型 |
| 报告 | `report_draft.py` 模板 + 可选 LLM 润色 + 事实回查 | 导出 Markdown 底稿，不是 STR 报文 |
| 脱敏 | `privacy.py` PrivacyMap（进模前替换，签发前还原） | 无独立密钥管理系统 |
| 权限 | CORS 默认只放行本地 Vite；`HUICHA_DEMO_TOKEN` 为竞赛口令 | **不是**银行 SSO |

前端工作台：`frontend/src/App.jsx` + `CasePanels.jsx` + `InvestigateFlow.jsx`。证据图、时间线均为自绘 Ant Design 组件，无 D3 / 图数据库。

---

## 4. 数据与实验

- **数据**：全部 `synthetic`；路演案 A/B/C/D/F/L + 约 80 条模板精标。
- **机制验证**：`python -m app.experiments`（stub，不是准确率）。
- **能力评测框架**：`experiments/benchmark.py`，指标仍为 **Not evaluated yet**。

---

## 5. 刻意没上的东西

无 Docker Compose、无 Redis/消息队列、无向量库、无生产权限模型、无前端状态库（Redux 等）、无 OpenAI/LangChain SDK。需要离线演示时开 stub，不调百炼。

更细的架构、打分公式与答辩口径见 `慧查AML-技术文档（供商业计划最终报告）.md`；启动步骤见 `huicha-aml/README.md`。
