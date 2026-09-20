# DRAWIO_REPORT

系统架构 / 岗位作业 / 调查编排三张非数据图。口径对齐 `huicha-aml/README.md` §3–§5 与双控签发（调查员提交、复核岗签发、禁止自动报送）。

CLI：`C:\Program Files\draw.io\draw.io.exe`  
Lint：`fig_roadmap` / `fig_flow_biz` / `fig_pipeline` 全部 OK。

未画：`fig_flow_q2`、`fig_model`、`fig_index_system`（本作品不是分问建模题，也不是评价指标体系）。

## 清单

| 文件 | 图种 | 用途 |
|------|------|------|
| `figures/fig_roadmap.drawio` | 路线图/分层架构 | 接入–编排–治理 + 底层能力 |
| `figures/fig_flow_biz.drawio` | 业务流程图 | 领案→调查→事实闸→双控签发 |
| `figures/fig_pipeline.drawio` | 编排流水线 | Planner…Reporter→人工双控 |

各图另有预览 PNG（`--width 2000`，无 `-e`）与论文 PDF（`-e -b 16`）。

## 构图五要素

### fig_roadmap

- 叙事: 告警进入待办后，只读编排给出三档建议，经核验护栏交给双控签发，能力层只提供工具与存储，不改变决策权。
- 层次: 接入 / 编排 / 治理 / 能力
- 节点角色: 平行四边形输入；圆角/直角处理；process 子过程；document 记录；红框硬约束
- 回流: 无（岗位回流见业务流程图）
- 与数据图分工: 不重复实验指标或 token 消耗图

### fig_flow_biz

- 叙事: 调查员领案并跑编排；事实硬问题必须补证重查；无硬问题才提交；复核同意后只产生已签草稿，系统不报送。
- 层次: 单列主路径，左侧两条回流走廊
- 节点角色: 椭圆起止；平行四边形 I/O；process 调查/复核；菱形判定
- 回流: 「事实回查硬问题=是」回到执行调查；「同意签发=否」退回领案
- 与数据图分工: 不画三档分布或 Macro-F1

### fig_pipeline

- 叙事: 窗口流水经规划取证与脱敏后，由 Analyst/Judge 给出建议，Skeptic 与 Guardrail 闸门后再成稿，Assemble 的 `can_sign` 之后才允许人工双控。
- 层次: 取证 / 判断 / 成稿
- 节点角色: 输入输出平行四边形；处理；检验；红框硬闸
- 回流: 无（硬问题回流在业务图）
- 与数据图分工: 不重复消融实验表

## 视觉自检

| 图 | Status | Iterations | 说明 |
|----|--------|------------|------|
| fig_roadmap | PASS | 2 | 第 1 轮核验→提交连线穿过能力层；已把治理上移、能力垫底，连线走编排–治理走廊 |
| fig_flow_biz | PASS | 2 | 第 1 轮两条回流共用竖线；已拆成近距补证环与左侧退回走廊 |
| fig_pipeline | PASS | 1 | 层间转折走右走廊，未穿盒 |

## 给正文的 caption

**图：循证慧查分层架构。** 上游告警进入分岗待办后，Planner/Collector 只读取证，Judge 输出三档建议，Skeptic 与政策护栏作硬边界；调查员提交、复核岗签发，系统禁止自动报送。Note. 能力层为只读工具、法规检索、LLM 与 SQLite，不参与处置权。

```latex
\includegraphics[width=0.96\textwidth]{fig_roadmap.pdf}
```

**图：告警后调查与双控签发流程。** 事实回查硬问题阻断签发并回流重查；复核不同意则退回调查员；同意后仅落已签草稿。Note. 作业按调查岗提交、复核岗签发分权，不出现具体人名。

```latex
\includegraphics[width=0.55\textwidth]{fig_flow_biz.pdf}
```

**图：调查编排流水线。** 进模前脱敏，护栏不与模型加权，`can_sign` 为签发前最后闸门。Note. Planner 为确定性白名单规划，不由模型决定调哪些工具。

```latex
\includegraphics[width=0.96\textwidth]{fig_pipeline.pdf}
```

## Trace

| artifact_id | 数据/口径源 | 变换 | 主张 | 建议引用位置 |
|-------------|-------------|------|------|----------------|
| fig_roadmap | README §4–§5 | `figures/fig_roadmap.drawio` | Agent 只建议，人签发 | 系统架构节 |
| fig_flow_biz | 3 分钟脚本双控步骤 | `figures/fig_flow_biz.drawio` | 硬事实与复核均可回流 | 业务流程节 |
| fig_pipeline | README Agent 表 | `figures/fig_pipeline.drawio` | 取证→判断→成稿顺序固定 | 方法/编排节 |
