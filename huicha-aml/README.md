# 慧查 AML

面向反洗钱合规调查的演示工作台（工行杯原型）。  
**不连接真实银行。** 上游检测用合成告警模拟；本系统只做「告警后调查草稿 + 人工签发」。

## 能力摘要

- Planner 按告警类型声明工具子集；Collector 经 `@tool` **真实留痕**
- Analyst 规则打底分；Challenger = **规则先验 + LLM 有界 delta（±0.15，证据校验）**
- Reporter 百炼润色；**脱敏进模**；事实回查；可缓存
- 精标约 **30+** 条（含路演 A/B/C/F「继续观察」）；`/api/feedback` 闭环看板
- 实验：`py -m app.experiments` → `huicha-aml/experiments/RESULTS.md`

## 启动

```bat
cd huicha-aml\backend
py -m pip install -r requirements-dev.txt
py -m uvicorn app.main:app --reload --port 8000
```

```bat
cd huicha-aml\frontend
npm install
npm run dev
```

浏览器 http://127.0.0.1:5173 。复制 `backend/.env.example` → `.env` 填百炼 Key。  
**改种子后请删除 `backend/huicha.db` 再启动。**

## 测试与实验

```bat
cd huicha-aml\backend
py -m pytest -q
py -m app.experiments
```

## 路演

快捷键 1/2/3/4 → 案例 A/B/C/F。详见 `路演.md`。
