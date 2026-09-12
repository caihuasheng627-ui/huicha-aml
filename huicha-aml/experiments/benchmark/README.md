# Benchmark 数据说明

当前仓库只有**合成**案件。

- `golden_set.json`：路演 + 模板精标 ID（与规则分支同源，不是独立人工标注）
- `test_set.json`：预留 hold-out 槽位（TODO）
- `independent_set.json`：与规则模板**不同源**的 vignette 合成标注集（含 `annotation_reason`）
- `build_independent_set.py`：生成独立集

能力评估：

```bash
# 仅查看框架状态
python experiments/benchmark.py

# 独立集 + 真实百炼（须配置 backend/.env 的 DASHSCOPE_API_KEY）
python experiments/benchmark.py --real
```

禁止把本目录数字写成「准确率 98%」。结论须人工签发。
