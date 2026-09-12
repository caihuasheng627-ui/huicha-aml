# Benchmark 数据说明（v2）

- `golden_set.json`：路演 + 模板精标（与规则同源，非独立人工标注）
- `test_set.json`：预留 hold-out
- `independent_set.json`：组合采样独立合成集（**n_unique 必须 ≥ 200**，无标签泄漏）
- `build_independent_set.py`：生成器
- `runs/`：真实调用原始 jsonl（默认不入库）

```bash
# 重生独立集
python experiments/benchmark/build_independent_set.py

# 框架状态 + 离线基线
python experiments/benchmark.py
python experiments/benchmark.py --baselines-only

# 产品 Judge 真实评估（须 DASHSCOPE_API_KEY）
python experiments/benchmark.py --real --limit 5   # 冒烟
python experiments/benchmark.py --real            # 全量
```

禁止把本目录数字写成产品准确率。结论须人工签发。
v1（Macro-F1≈0.69）已因实验硬伤降级，见 RESULTS.md。
