# Benchmark 数据说明（v3）

- `golden_set.json`：路演 + 模板精标（与规则同源，非独立人工标注）
- `test_set.json`：预留 hold-out
- `independent_set.json`：组合采样独立合成集（**n_unique 必须 ≥ 200**，无标签泄漏）
  - v3：每个 case 先生成真实结构的流水，再调产品 `analyst_rules.analyze()` 得到规则层 findings；
    叙事项带 `support/counter/context` 极性；**不向 Judge 传 `missing_evidence`**；
    证据编号用 `TX-`（流水）/ `IX-`（叙事项）/ `KB-`（知识），与产品 `enrich_judge` 契约一致
- `blind_set.json`：例举词盲区 hold-out
- `struct_set.json`：结构盲区 hold-out（禁词同盲区，且流水不触发 structuring/funnel/night-out/layering）
- `real_holdout.json`：真实 hold-out 导入槽（占位样例 `data_note=placeholder`，不写入 RESULTS 主表）
- `build_independent_set.py`：生成器（`--variant v3|nopolarity|blind|blind_struct`）
- `runs/`：真实调用原始 jsonl，文件名带 prompt 版本（`<ts>_<judge_vN>.jsonl`）

```bash
# 重生独立集
python experiments/benchmark/build_independent_set.py

# 框架状态 + 离线基线
python experiments/benchmark.py
python experiments/benchmark.py --baselines-only

# 产品 Judge 真实评估（须 DASHSCOPE_API_KEY；默认 prompt = 产品 prompt_version("judge")）
python experiments/benchmark.py --real --limit 5 --no-write   # 冒烟，不写结果
python experiments/benchmark.py --real                        # 全量

# 消融：同一集上换 prompt 版本（只影响本次实验，不改产品默认）
python experiments/benchmark.py --real --prompt judge_v2
```

`RESULTS.json` 中 `independent_real_model` 是最近一次；`independent_real_model_runs[<prompt>]` 按 prompt 版本各留一份，
≥2 个版本时自动生成 `independent_ablation` 并渲染到 `RESULTS.md`。

```bash
# 结构盲区 / 真实 hold-out 槽
python experiments/benchmark/build_independent_set.py --variant blind_struct
python experiments/benchmark.py --real --set blind_struct --prompt judge_v3
python experiments/benchmark/export_boundary.py
python experiments/benchmark/export_gold_review.py
python experiments/benchmark/score_gold_review.py
python experiments/benchmark/import_real_cases.py --placeholder
python experiments/benchmark.py --real --set real --limit 5 --no-write
```

`judge_v4` 仅消融：`--prompt judge_v4`。默认产品仍是 `judge_v3`。

禁止把本目录数字写成产品准确率。结论须人工签发。
v1（Macro-F1≈0.69）与 v2 集（missing_evidence 泄漏、无规则层）结果均不得与 v3 混比，见 RESULTS.md / REAL_MODEL_REPORT.md。
