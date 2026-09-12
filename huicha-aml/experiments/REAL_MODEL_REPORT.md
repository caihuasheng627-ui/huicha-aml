# 循证慧查 · 真实模型测试报告（状态说明）

**日期**：2026-09-12（v2 协议就绪，真实数字待重跑）

## 诚实声明

- v1 报告中的 Macro-F1≈0.69 **已降级**，不能代表模型能力。
- 原因：约 10 个唯一输入、标签泄漏、自写 prompt 贴合测试集、未走产品 Judge、解析失败并入 observe、Evidence gold 不合理。
- v2 已修复实验构造（n_unique=240、去泄漏、judge_v2 流水线、原始输出落盘、分组指标与基线）。
- 请在配置 `DASHSCOPE_API_KEY` 后执行：

```bash
python experiments/benchmark.py --real
```

并将新结果写回 `RESULTS.md` / 本报告。**不是生产准确率；须人工签发。**

## 当前离线基线（v2 集，n=240）

| 基线 | Macro-F1 |
| --- | ---: |
| always_suggest_report | 0.2082 |
| keyword_match | 0.8670 |

## 产物

- 协议与自测：`SELF_TEST_PLAYBOOK.md`
- 数据：`benchmark/independent_set.json`
- 跑批日志：`benchmark/runs/*.jsonl`
