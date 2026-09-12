# 改进后自测流程（v2 协议）

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

可选泄漏自检：

```powershell
py -c "import json,re; d=json.load(open('experiments/benchmark/independent_set.json',encoding='utf-8'));
print('n_unique', d['n_unique']);
bad=[c['case_id'] for c in d['cases'] if '叙事族' in json.dumps(c['vignette'],ensure_ascii=False) or '关键线索' in json.dumps(c['vignette'],ensure_ascii=False)];
print('leaks', bad[:5], 'count', len(bad))"
```

## 4. 冒烟 → 全量

```powershell
Copy-Item experiments\RESULTS.json experiments\RESULTS.prev.json -ErrorAction SilentlyContinue
py experiments\benchmark.py --real --limit 5
# 看 experiments/benchmark/runs/*.jsonl 是否有 raw_text；parse_failures 是否异常高
py experiments\benchmark.py --real
```

## 5. 读哪些数

1. **相对基线**：模型 Macro-F1 是否明显高于 `always_suggest_report`（≈0.21）  
2. **parse_failures / call_errors**：不应并进 observe；应单独接近 0  
3. **verify_pass_rate**：产品证据契约通过率  
4. **by_tag**：是「某个叙事整族错」还是「同族抖动」  
5. **Evidence 支持侧 / 反证侧** P&R  
6. **混淆矩阵**（仅 parse 成功样本）

## 6. 不要做的事

- 不要把 v1（0.69）与 v2 混比  
- 不要在 SYSTEM/judge_v2 里列举测试集叙事族  
- 不要开 stub 却写入「真实模型」  
- 不要把 keyword 基线 0.87 当成「模型该打到的分」——它只说明合成文本仍有表面线索

## 7. 口令

```powershell
cd huicha-aml\backend; py -m pytest -q
cd ..
Remove-Item Env:HUICHA_LLM_STUB -ErrorAction SilentlyContinue
py experiments\benchmark.py --baselines-only
py experiments\benchmark.py --real --limit 5
py experiments\benchmark.py --real
```
