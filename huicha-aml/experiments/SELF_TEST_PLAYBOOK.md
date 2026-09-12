# 改进后自测流程（v3 协议）

**口径**：实验对照，不是生产准确率；须人工签发。

## 0. 一次只改一类

| 改动 | 动作 |
| --- | --- |
| Judge / 护栏 / prompts | pytest → `--real`（不必重生集） |
| 数据生成器 / 金标 | 重生 `independent_set.json` → 确认 n_unique≥200 → `--real` |
| 只想核对基线 | `--baselines-only`（不耗额度） |

## 1. 环境

```powershell
cd <repo>\huicha-aml
Remove-Item Env:HUICHA_LLM_STUB -ErrorAction SilentlyContinue
# backend/.env 需有 DASHSCOPE_API_KEY
```

## 2. 单元测试

```powershell
cd backend
py -m pytest -q
```

## 3. 数据集健全性（改生成器后必做）

```powershell
cd ..
py experiments\benchmark\build_independent_set.py
py experiments\benchmark.py --baselines-only
```

检查：

- `n_unique` ≥ 200 且接近 `n`
- 基线 always_report Macro-F1 应很低（≈0.2）
- keyword 基线仅作对照，**不是**能力上限证明

泄漏自检已固化为单测 `backend/tests/test_independent_benchmark_set.py`：

- 输入不含 `叙事族/关键线索/干扰线索/合成/占位/gold/annotation_reason`
- `vignette` 内没有 `missing_evidence` 输入（v2 的 observe 泄漏源）
- 证据编号只用 `TX-/IX-/KB-/C-/ACC-`（产品 `enrich_judge` 会过滤 `EV-`）
- 排除族叙事项必有 `counter` 极性，上报族必有规则层 support finding（structuring/funnel/night-out/layering）

## 4. 冒烟 → 全量

```powershell
Copy-Item experiments\RESULTS.json experiments\RESULTS.prev.json -ErrorAction SilentlyContinue
py experiments\benchmark.py --real --limit 5 --no-write
# 看 experiments/benchmark/runs/*_judge_vN.jsonl 是否有 raw_text；parse_failures 是否异常高
py experiments\benchmark.py --real
# 消融：同一集上换 prompt（不改产品默认）
py experiments\benchmark.py --real --prompt judge_v2
# 有效性：盲区 hold-out / 去极性（不改产品默认）
py experiments\benchmark\build_independent_set.py --variant blind
py experiments\benchmark\build_independent_set.py --variant nopolarity
py experiments\benchmark.py --real --set blind --prompt judge_v3
py experiments\benchmark.py --real --set nopolarity --prompt judge_v2
```

## 5. 读哪些数

1. **相对基线**：模型 Macro-F1 是否明显高于 `always_suggest_report`（≈0.21）  
2. **parse_failures / call_errors**：不应并进 observe；应单独接近 0  
3. **verify_pass_rate**：产品证据契约通过率  
4. **by_tag**：是「某个叙事整族错」还是「同族抖动」  
5. **Evidence 支持侧 / 反证侧** P&R（只在叙事项 `IX-` 上计算）  
6. **混淆矩阵**（仅 parse 成功样本）  
7. **confidence 直方图 / 去重取值数 / 标准差**：是否所有样本都给同一个数  
8. **observe 带 missing_evidence 比例**：judge_v3 要求 observe 必列待补材料  
9. **消融表**（`RESULTS.md` 末节 / `RESULTS.json.independent_ablation`）：prompt 版本是唯一变量

## 6. 不要做的事

- 不要把 v1（0.69）、v2 集（0.17，有 missing_evidence 泄漏且无规则层）与 v3 集混比  
- 不要在 SYSTEM/judge_v3 里列举测试集叙事族（判定标准只写可操作边界，不写族名）  
- 不要开 stub 却写入「真实模型」  
- 不要把 keyword 基线 0.87 当成「模型该打到的分」——它只说明合成文本仍有表面线索

## 7. 口令

```powershell
cd huicha-aml\backend; py -m pytest -q
cd ..
Remove-Item Env:HUICHA_LLM_STUB -ErrorAction SilentlyContinue
py experiments\benchmark.py --baselines-only
py experiments\benchmark.py --real --limit 5 --no-write
py experiments\benchmark.py --real
py experiments\benchmark.py --real --prompt judge_v2   # 消融
```
