# 慧查 AML

面向反洗钱合规调查的演示工作台（工行杯原型）。  
**不连接真实银行。** 上游检测用合成告警模拟，本系统只做「告警后调查草稿 + 人工签发」。

## 最终形态

浏览器三栏：告警队列 | Agent 简报与报告草稿 | 证据链/子图/审计。  
路演点案例 A（误报排除）、B（拆分）、C（归集）。

## 启动

需要：Windows 上的 `py`（Python 3.11）和 Node.js。

终端 1（后端）：

```bat
cd huicha-aml\backend
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --port 8000
```

终端 2（前端）：

```bat
cd huicha-aml\frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173

也可双击 `start.bat`。路演步骤见 `路演.md`。快捷键 `1` `2` `3` 打开案例 A/B/C。

首次启动会自动写入 SQLite 合成库 `backend/huicha.db`。若改了种子数据，删掉该文件后重启后端。

## 大模型（必选）

复制 `backend/.env.example` 为 `backend/.env`，填入阿里云百炼 `DASHSCOPE_API_KEY`。  
默认模型：`deepseek-v4-flash-0731`。Challenger / Reporter **必须走 API**，失败会直接报错，**不再回退模板文案**。  
结论档位仍由规则打分；事实回查照旧。

**不要把 `.env` 提交到 GitHub。**

## 测试

```bat
cd huicha-aml\backend
py -m pip install -r requirements.txt
py -m pytest -q
```

会固化路演 A/B/C/D 结论、幻觉拦截、万元格式事实回查（测试中 stub 百炼 HTTP，生产无模板回退）。

## 演示路径

1. 点「案例 A」→ 启动调查 Agent → 结论应为排除。
2. 点「案例 B」→ 拆分 + 夜间集中转出 → 建议上报。
3. 点「案例 C」→ 多账户归集且对手命中演示名单 → 建议上报。
4. 事实回查通过后可「确认签发」；打开右上角「注入幻觉」再重跑，签发按钮应灰掉。
5. 案例 A 打开右上角关掉 Challenger 再重跑，结论应从排除变为建议上报（消融）。
