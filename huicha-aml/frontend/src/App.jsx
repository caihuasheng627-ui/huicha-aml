import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Divider,
  Input,
  Space,
  Switch,
  Table,
  Tag,
  Timeline,
  message,
} from "antd";
import {
  decide,
  downloadExport,
  fetchAlerts,
  fetchDetail,
  fetchFeedback,
  fetchHealth,
  fetchMetrics,
  getDemoToken,
  runInvestigate,
  setDemoToken,
} from "./api";
import { CounterfactualBox, EvidenceLists, RejectedClaims, RegulationBox, RiskFactors, TxTimeline, VerifiedClaims } from "./CasePanels.jsx";
import { InvestigateTheater, PipelineRail, usePipelinePlayback } from "./InvestigateFlow.jsx";

const HUMAN = {
  confirm: "已记录签发",
  modify: "修改后采纳",
  reject: "已驳回",
};

const STATUS = {
  pending: { text: "待调查", color: "default" },
  investigating: { text: "调查中", color: "processing" },
  closed: { text: "已排除关闭", color: "success" },
  monitoring: { text: "持续监测", color: "warning" },
  ready_to_file: { text: "待复核上报", color: "error" },
  modified: { text: "人工已改", color: "warning" },
};

const CONC = {
  exclude: "排除",
  observe: "观察",
  suggest_report: "建议上报",
};

const AUDIT_ACTION = {
  investigate: "生成草稿",
  decide: "人工处置",
  tool: "调取工具",
  tools: "调取工具",
};

const TOKEN_SPLIT = /(EV-[A-Z0-9\-]+|TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|C-[A-Z0-9]+|KB-[A-Z0-9\-]+)/;
const TOKEN_ONE = /^(EV-[A-Z0-9\-]+|TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|C-[A-Z0-9]+|KB-[A-Z0-9\-]+)$/;

const DEMOS = [
  { id: "ALT-A-20260910", key: "1", label: "案例 A 排除" },
  { id: "ALT-B-20260910", key: "2", label: "案例 B 拆分" },
  { id: "ALT-C-20260910", key: "3", label: "案例 C 归集" },
  { id: "ALT-F-20260910", key: "4", label: "案例 F 观察" },
  { id: "ALT-L-20260910", key: "5", label: "案例 L 多层" },
];

function yuan(n) {
  const x = Number(n);
  if (Number.isNaN(x)) return String(n);
  if (Math.abs(x) >= 10000) return `${(x / 10000).toFixed(2)} 万元`;
  return `${x.toLocaleString()} 元`;
}

function nowText() {
  return new Date().toLocaleString("zh-CN", { hour12: false });
}

function shortLabel(s, n = 8) {
  const t = String(s || "");
  return t.length > n ? `${t.slice(0, n)}…` : t;
}

function isChannelToken(id, prefix) {
  return id === `${prefix}-AGG` || String(id).startsWith(`${prefix}-`);
}

function evidenceMatches(e, selected) {
  if (!selected) return true;
  if (String(selected).startsWith("KB-") || String(selected).startsWith("EV-")) return false;
  if (e.id === selected) return true;
  if (e.from_account === selected || e.to_account === selected) return true;
  if (isChannelToken(selected, "CASH") && (e.from_account?.startsWith("CASH-") || e.to_account?.startsWith("CASH-"))) {
    return true;
  }
  if (isChannelToken(selected, "POS") && (e.from_account?.startsWith("POS-") || e.to_account?.startsWith("POS-"))) {
    return true;
  }
  return false;
}

function edgeHot(e, selected) {
  if (!selected) return false;
  if (e.id === selected || (e.tx_ids || []).includes(selected)) return true;
  if (e.source === selected || e.target === selected) return true;
  if (isChannelToken(selected, "CASH") && (e.source === "CASH-AGG" || e.target === "CASH-AGG")) return true;
  if (isChannelToken(selected, "POS") && (e.source === "POS-AGG" || e.target === "POS-AGG")) return true;
  return false;
}

function nodeHot(n, selected, hotEdges) {
  if (!selected) return false;
  if (n.id === selected) return true;
  if (isChannelToken(selected, "CASH") && n.id === "CASH-AGG") return true;
  if (isChannelToken(selected, "POS") && n.id === "POS-AGG") return true;
  return hotEdges.some((e) => e.source === n.id || e.target === n.id);
}

function auditText(x) {
  let detail = x.detail || "";
  try {
    const j = JSON.parse(detail);
    if (j.decision) detail = `${HUMAN[j.decision] || j.decision}${j.note ? `：${j.note}` : ""}`;
    else if (j.summary) detail = j.summary;
    else if (j.tool) detail = `${j.tool} ${j.records ?? ""} 条`;
  } catch {
    /* already human text */
  }
  const actor = x.actor === "agent" ? "系统" : "调查员";
  return {
    title: `${actor} · ${AUDIT_ACTION[x.action] || x.action}`,
    detail,
    time: x.created_at || "",
  };
}

function ReportText({ text, issues, onSelect }) {
  const bad = new Set((issues || []).map((x) => x.token));
  const parts = String(text || "").split(TOKEN_SPLIT);
  return (
    <div className="report-box">
      {parts.map((p, i) => {
        if (!p) return null;
        if (bad.has(p)) return <mark key={i}>{p}</mark>;
        if (TOKEN_ONE.test(p)) {
          return (
            <button key={i} type="button" className="token" onClick={() => onSelect(p)}>
              {p}
            </button>
          );
        }
        return <span key={i}>{p}</span>;
      })}
    </div>
  );
}

function Graph({ graph, selected, onSelect }) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const layout = useMemo(() => {
    const cx = 180;
    const cy = 100;
    const others = nodes.filter((n) => n.kind !== "center");
    const map = {};
    nodes.forEach((n) => {
      if (n.kind === "center") map[n.id] = { x: cx, y: cy, ...n };
    });
    const r = others.length > 6 ? 68 : 84;
    others.forEach((n, i) => {
      const a = (Math.PI * 2 * i) / Math.max(others.length, 1) - Math.PI / 2;
      map[n.id] = { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * 64, ...n };
    });
    return map;
  }, [nodes]);

  const hotEdges = edges.filter((e) => edgeHot(e, selected));

  return (
    <div className="graph">
      <svg className="graph-live" viewBox="0 0 360 210" preserveAspectRatio="xMidYMid meet">
        {edges.map((e, i) => {
          const a = layout[e.source];
          const b = layout[e.target];
          if (!a || !b) return null;
          const hot = edgeHot(e, selected);
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={`${e.source}-${e.target}-${e.id}`}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={hot ? "#c8161d" : "#94a3b8"}
                strokeWidth={hot ? 2.4 : 1.1}
                style={{ animationDelay: `${i * 40}ms` }}
              />
              {e.amount != null && (
                <text x={mx} y={my - 4} textAnchor="middle" fill={hot ? "#9f1239" : "#64748b"} fontSize="8">
                  {yuan(e.amount)}
                  {e.count > 1 ? ` · ${e.count}笔` : ""}
                </text>
              )}
            </g>
          );
        })}
        {Object.values(layout).map((n) => {
          const hot = nodeHot(n, selected, hotEdges);
          const fill =
            n.kind === "watch" ? "#c8161d" : n.kind === "center" ? "#0a1628" : n.kind === "channel" ? "#0f7b4a" : "#1b4f8a";
          return (
            <g key={n.id} onClick={() => onSelect?.(n.id)} style={{ cursor: "pointer" }}>
              <title>{n.label || n.id}</title>
              <circle
                cx={n.x}
                cy={n.y}
                r={n.kind === "center" ? 15 : hot ? 11 : 9}
                fill={fill}
                stroke={hot ? "#c8161d" : "#fff"}
                strokeWidth="2"
              />
              <text x={n.x} y={n.y + 22} textAnchor="middle" fill="#334155" fontSize="10">
                {shortLabel(n.label || n.id, 7)}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="graph-legend" aria-hidden="true">
        <span>
          <i className="dot center" />
          主体
        </span>
        <span>
          <i className="dot peer" />
          对手方
        </span>
        <span>
          <i className="dot channel" />
          渠道
        </span>
        <span>
          <i className="dot watch" />
          关注名单
        </span>
      </div>
    </div>
  );
}

function ScoreBreakdown({ scoring, label }) {
  if (!scoring) return null;
  const rows = [
    { k: "规则底分", v: scoring.base },
    { k: "质疑先验", v: scoring.rule_prior },
    { k: "模型 Δ", v: scoring.llm_delta },
  ];
  const final = Number(scoring.final ?? 0);
  const pin = Math.max(2, Math.min(98, final * 100));
  return (
    <div className="score-break">
      <div className="score-break-hd">
        打分拆解
        <b className={conclusionTone(label)}>{label}</b>
      </div>
      <ul>
        {rows.map((r) => {
          const n = Number(r.v ?? 0);
          return (
            <li key={r.k}>
              <span>{r.k}</span>
              <em className={n < 0 ? "down" : n > 0 ? "up" : ""}>
                {n > 0 ? "+" : ""}
                {n.toFixed(2)}
              </em>
            </li>
          );
        })}
      </ul>
      <div className="score-track" title="0.35 排除 / 0.55 上报">
        <i className="tick" style={{ left: "35%" }} />
        <i className="tick" style={{ left: "55%" }} />
        <i className="pin" style={{ left: `${pin}%` }} />
      </div>
      <div className="score-track-cap">
        <span>排除</span>
        <span>观察</span>
        <span>上报</span>
      </div>
    </div>
  );
}

function FlowBars({ baseline }) {
  if (!baseline) return null;
  const inn = Number(baseline.sample_in_sum || 0);
  const out = Number(baseline.sample_out_sum || 0);
  const max = Math.max(inn, out, 1);
  return (
    <div className="flow-bars">
      <div className="flow-row">
        <span>流入 {baseline.sample_in_count ?? 0} 笔</span>
        <div className="flow-bar">
          <i className="in" style={{ width: `${(inn / max) * 100}%` }} />
        </div>
        <b>{yuan(inn)}</b>
      </div>
      <div className="flow-row">
        <span>流出 {baseline.sample_out_count ?? 0} 笔</span>
        <div className="flow-bar">
          <i className="out" style={{ width: `${(out / max) * 100}%` }} />
        </div>
        <b>{yuan(out)}</b>
      </div>
    </div>
  );
}

function conclusionTone(label) {
  if (label === "排除") return "ok";
  if (label === "继续观察") return "warn";
  return "risk";
}

export default function App() {
  const [alerts, setAlerts] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [current, setCurrent] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const [useChallenger, setUseChallenger] = useState(true);
  const [injectHallucination, setInjectHallucination] = useState(false);
  const [selected, setSelected] = useState("");
  const [openSteps, setOpenSteps] = useState({});
  const [onlyDemo, setOnlyDemo] = useState(true);
  const [q, setQ] = useState("");
  const [clock, setClock] = useState(nowText());
  const [offline, setOffline] = useState(false);
  const [llmOff, setLlmOff] = useState(false);
  const [healthInfo, setHealthInfo] = useState(null);
  const [needsToken, setNeedsToken] = useState(false);
  const [tokenDraft, setTokenDraft] = useState(() => getDemoToken());
  const [feedback, setFeedback] = useState(null);
  const [invError, setInvError] = useState(false);
  const openSeq = useRef(0);
  const inv = detail?.investigation;
  const playback = usePipelinePlayback({ running: loading, failed: invError });
  const showTheater = playback.phase === "playing" || playback.phase === "holding" || playback.phase === "error";

  async function loadList() {
    let health = null;
    try {
      health = await fetchHealth();
      setHealthInfo(health);
      setLlmOff(health?.llm === "off");
    } catch (e) {
      setOffline(true);
      throw e;
    }
    try {
      const [list, m, fb] = await Promise.all([
        fetchAlerts(),
        fetchMetrics(),
        fetchFeedback().catch(() => null),
      ]);
      setAlerts(list);
      setMetrics(m);
      setFeedback(fb);
      setNeedsToken(false);
      setOffline(false);
    } catch (e) {
      const msg = String(e?.message || "");
      if (health?.auth === "demo_token" || msg.includes("演示口令")) {
        setNeedsToken(true);
        setOffline(false);
      } else {
        setOffline(true);
      }
      throw e;
    }
  }

  async function open(id) {
    const seq = ++openSeq.current;
    setCurrent(id);
    setSelected("");
    const d = await fetchDetail(id);
    if (seq !== openSeq.current) return;
    setDetail(d);
    setNote(d.human_note || "");
  }

  useEffect(() => {
    loadList().catch((e) => message.error(e.message.includes("调查服务") || e.message.includes("fetch") ? "无法连接调查服务，请先启动后端 8000 端口" : e.message));
    const t = setInterval(() => setClock(nowText()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      const hit = DEMOS.find((d) => d.key === e.key);
      if (hit) open(hit.id).catch((err) => message.error(err.message));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function onInvestigate(id = current) {
    if (!id || loading) return;
    setCurrent(id);
    setInvError(false);
    setLoading(true);
    open(id).catch(() => {});
    try {
      await runInvestigate(id, { useChallenger, injectHallucination });
      await open(id);
      await loadList();
      message.success("调查草稿已生成，待人工签发");
    } catch (e) {
      setInvError(true);
      message.error(e.message || "调查失败");
    } finally {
      setLoading(false);
    }
  }

  async function onDecide(decision) {
    if (!current) return;
    try {
      await decide(current, decision, note);
      await open(current);
      await loadList();
      message.success("处置意见已写入审计");
    } catch (e) {
      message.error(e.message);
    }
  }

  function selectEvidence(id) {
    const graph = inv?.evidence_graph || [];
    let resolved = id;
    if (String(id || "").startsWith("EV-")) {
      const hit = graph.find((e) => e.evidence_id === id);
      if (hit) {
        const raw = String(hit.raw_reference || "");
        const tx = raw
          .split(",")
          .map((s) => s.trim())
          .find((s) => /^(TX-|KB-)/.test(s));
        resolved = tx || hit.source_id || id;
      }
    }
    setSelected(resolved);
    requestAnimationFrame(() => {
      const el = document.getElementById(`ev-${resolved}`) || document.getElementById(`ev-${id}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  const listEvidence = (inv?.evidence || []).filter((e) => evidenceMatches(e, selected));
  const txRows = listEvidence
    .filter((e) => e.type === "transaction")
    .map((e) => ({
      key: e.id,
      id: e.id,
      occurred_at: e.occurred_at || "",
      channel: e.channel || "",
      amount: e.amount,
      summary: e.summary,
    }));

  const queue = alerts
    .filter((a) => !onlyDemo || a.demo_tag)
    .filter((a) => !q || `${a.title}${a.customer_name}${a.alert_type}${a.id}`.includes(q));

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <b>查</b>
          </div>
          <div className="brand-text">
            <strong>慧查 AML</strong>
            <span>AI 推理 · 规则边界 · 证据事实 · 人做决策</span>
          </div>
        </div>
        <div className="staff">
          <span>
            岗位 <b>反洗钱合规</b>
          </span>
          <span>
            调查员 <b>陈析</b>　002183
          </span>
          <span>{clock}</span>
          <span className="env">
            合成数据 · 竞赛原型 · 须人签
            {healthInfo?.auth === "demo_token" ? " · 演示口令" : " · 接口开放"}
            {healthInfo?.kb_docs != null ? ` · 知识库 ${healthInfo.kb_docs} 条` : ""}
          </span>
        </div>
      </header>

      <div className="toolbar">
        {DEMOS.map((d) => (
          <Button key={d.id} size="small" type={current === d.id ? "primary" : "default"} disabled={loading} onClick={() => onInvestigate(d.id)}>
            {d.label}
          </Button>
        ))}
        <span className="toolbar-sep" />
        <label>
          质疑复核
          <Switch size="small" checked={useChallenger} onChange={setUseChallenger} />
        </label>
        <label>
          幻觉演示
          <Switch size="small" checked={injectHallucination} onChange={setInjectHallucination} />
        </label>
        <span className="hint" style={{ margin: 0 }}>
          快捷键 1–5 打开 A/B/C/F/L；按钮会直接跑调查。AI 不得自动报送。
        </span>
        {healthInfo?.auth === "demo_token" && (
          <>
            <span className="toolbar-sep" />
            <Input.Password
              size="small"
              placeholder="演示口令 X-Huicha-Token"
              value={tokenDraft}
              onChange={(e) => setTokenDraft(e.target.value)}
              style={{ width: 220 }}
            />
            <Button
              size="small"
              onClick={() => {
                setDemoToken(tokenDraft);
                loadList().catch((err) => message.error(err.message));
              }}
            >
              保存口令
            </Button>
          </>
        )}
      </div>

      <PipelineRail playback={playback} complete={Boolean(inv) && !showTheater} useChallenger={useChallenger} />

      <div className="workspace">
      {offline && (
        <Alert
          type="error"
          banner
          showIcon
          message="无法连接调查服务"
          description="请先启动后端：huicha-aml/backend 下执行 py -m uvicorn app.main:app --reload --port 8000"
        />
      )}
      {!offline && llmOff && (
        <Alert
          type="error"
          banner
          showIcon
          message="未配置 DASHSCOPE_API_KEY"
          description="Challenger/Reporter 强制走百炼 API。请在 backend/.env 填写密钥后再调查。"
        />
      )}
      {needsToken && (
        <Alert
          type="warning"
          banner
          showIcon
          message="需要演示口令"
          description="后端启用了 HUICHA_DEMO_TOKEN。这不是银行 SSO，只是竞赛原型的接口口令。请在上方填入口令后保存。"
        />
      )}
      {healthInfo?.limitations?.[0] && (
        <Alert
          type="info"
          banner
          showIcon
          message="诚实边界"
          description={`${healthInfo.limitations[0]}；知识库为关键词重叠检索（${healthInfo.kb_retrieval || "keyword-overlap"}），不是语义向量库。`}
        />
      )}

      <div className="layout">
        <aside className="col">
          <div className="col-title">
            <h3>待办告警</h3>
            <Tag>{metrics ? `${metrics.alerts} 条` : "—"}</Tag>
          </div>
          <div className="hint">
            上游检测已完成。本台只出草稿，不是监管结论。
            <Button type="link" size="small" onClick={() => setOnlyDemo((v) => !v)}>
              {onlyDemo ? "全部告警" : "路演案"}
            </Button>
          </div>
          {feedback && feedback.decisions && (
            <div className="hint" style={{ marginBottom: 8 }}>
              反馈闭环：采纳 {feedback.decisions.confirm} · 修改 {feedback.decisions.modify} · 驳回{" "}
              {feedback.decisions.reject}
              {metrics?.labeled ? ` · 模板精标 ${metrics.labeled}` : ""}
            </div>
          )}
          <Input
            size="small"
            allowClear
            placeholder="客户名称 / 告警类型 / 编号"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ marginBottom: 10 }}
          />
          {queue.length === 0 && <div className="hint">没有匹配的告警。</div>}
          {queue.map((a) => {
            const st = STATUS[a.status] || STATUS.pending;
            return (
              <div
                key={a.id}
                className={`queue-item ${current === a.id ? "active" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => open(a.id).catch((e) => message.error(e.message))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") open(a.id).catch((err) => message.error(err.message));
                }}
              >
                <div className="t">
                  {a.demo_tag ? (
                    <Tag color="red" style={{ marginRight: 6 }}>
                      {a.demo_tag}
                    </Tag>
                  ) : null}
                  {a.title}
                </div>
                <div className="m">
                  <span>
                    {a.customer_name} · {yuan(a.amount)}
                  </span>
                  <span>
                    {a.conclusion ? <Tag>{CONC[a.conclusion] || a.conclusion}</Tag> : null}
                    <Tag color={st.color}>{st.text}</Tag>
                  </span>
                </div>
              </div>
            );
          })}
        </aside>

        <main className="col">
          <div className="col-title">
            <h3>调查作业</h3>
            {detail?.alert && <span className="hint">{detail.alert.id}</span>}
          </div>
          {!current && (
            <div className="empty">
              <h4>领取告警，走完调查流水线</h4>
              <p className="hint">本台接在监测系统之后，只生成调查草稿，不上报、不记账。</p>
              <ol>
                <li>案例 A：批发企业大额频繁 → 建议排除（有经营反证）</li>
                <li>关闭「质疑复核」再跑 A：同一案可能变为建议上报</li>
                <li>案例 B / C：拆分与多账户归集 → 建议进入上报复核</li>
                <li>案例 L：A→B→C→D 短时多层转移（一键 Demo）</li>
                <li>打开「幻觉演示」：签发将被事实回查拦住</li>
                <li>右侧 Evidence Graph / 法规 / 流水均可点回原始数据</li>
              </ol>
            </div>
          )}
          {current && showTheater && (
            <InvestigateTheater
              playback={playback}
              useChallenger={useChallenger}
              injectHallucination={injectHallucination}
              onRetry={() => onInvestigate()}
              onBack={() => playback.reset()}
            />
          )}
          {current && !showTheater && (
            <div className={`dossier${playback.phase === "done" ? " is-revealed" : ""}`}>
              <div className="kpi">
                <div className={`kpi-card ${inv ? conclusionTone(inv.conclusion_label) : ""}`}>
                  <div className="k">建议结论</div>
                  <div className="v">{inv ? inv.conclusion_label : "未生成"}</div>
                </div>
                <div className="kpi-card">
                  <div className="k">规则分</div>
                  <div className="v">{inv ? Number(inv.confidence).toFixed(2) : "—"}</div>
                  {inv && (
                    <div className="conf-bar" aria-hidden="true">
                      <i style={{ width: `${Math.max(2, Math.min(98, Number(inv.confidence) * 100))}%` }} />
                    </div>
                  )}
                  <div className="hint" style={{ margin: "6px 0 0" }}>
                    {inv?.confidence_kind === "rule_score_not_calibrated" ? "规则打底，非校准置信度" : "非概率置信度"}
                  </div>
                </div>
                <div className="kpi-card">
                  <div className="k">耗时 / 工具次数</div>
                  <div className="v">
                    {inv?.comparison ? `${inv.comparison.agent_ms} ms · ${inv.comparison.tools_called} 次` : "—"}
                  </div>
                </div>
              </div>
              <Space wrap style={{ marginBottom: 10 }}>
                <Button type="primary" disabled={loading || llmOff} onClick={() => onInvestigate()}>
                  {inv ? "按当前策略重跑" : "开始调查"}
                </Button>
                {detail?.human_decision ? (
                  <Tag color="gold">{HUMAN[detail.human_decision]}</Tag>
                ) : (
                  <Tag>待签发</Tag>
                )}
                {inv?.use_challenger === false && <Tag color="orange">质疑角色已关</Tag>}
                {inv?.inject_hallucination && <Tag color="red">已注入幻觉</Tag>}
                {inv?.llm?.reporter || inv?.llm?.challenger ? (
                  <Tag color="blue">{inv.llm.model || "百炼已调用"}</Tag>
                ) : null}
              </Space>
              <div className="client-box">
                {detail?.alert?.upstream}
                {inv?.customer?.summary ? `。${inv.customer.summary}` : ""}
                {inv?.comparison
                  ? ` 工具 ${inv.comparison.tools_called} 次 · 要素 ${inv.comparison.elements_filled}/${inv.comparison.elements_total} · 证据可回溯。`
                  : ""}
              </div>
              {inv && (
                <div className="viz-row">
                  <ScoreBreakdown scoring={inv.scoring} label={inv.conclusion_label} />
                  <FlowBars baseline={inv.baseline} />
                </div>
              )}
              {inv?.case_v2 && (
                <div className="client-box">
                  案件 {inv.case_v2.case_id} · 建议 {inv.case_v2.recommendation_label} · 风险 {inv.case_v2.risk_level} ·
                  数据 {inv.data_note || "synthetic"} · Agent 不得自动报送
                </div>
              )}
              {inv && <RiskFactors risk={inv.risk} onSelect={selectEvidence} />}
              {inv && <VerifiedClaims rows={inv.challenger} onSelect={selectEvidence} />}
              {inv && <TxTimeline rows={inv.timeline} onSelect={selectEvidence} />}
              {inv && <CounterfactualBox cf={inv.counterfactual} />}
              {inv && <RegulationBox cites={inv.structured_report?.regulation_basis} onSelect={selectEvidence} />}
              {inv && <RejectedClaims rows={inv.rejected_claims} onSelect={selectEvidence} />}
              {inv?.fact_issues?.length > 0 && (
                <Alert
                  type="error"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="事实回查未通过，禁止签发"
                  description={inv.fact_issues.map((x) => x.token).join("、")}
                />
              )}

              {inv?.steps && (
                <>
                  <Divider plain orientation="left">
                    调查过程
                  </Divider>
                  <Timeline
                    items={inv.steps.map((s) => {
                      const defaultOpen = ["Analyst", "Challenger", "Reporter"].includes(s.role);
                      const opened = openSteps[s.role] ?? defaultOpen;
                      return {
                        color: s.role === "Challenger" && inv.use_challenger === false ? "gray" : "blue",
                        children: (
                          <div className="step" style={{ border: "none", paddingLeft: 0, margin: 0 }}>
                            <button
                              type="button"
                              className="role"
                              onClick={() =>
                                setOpenSteps((p) => ({
                                  ...p,
                                  [s.role]: !(p[s.role] ?? defaultOpen),
                                }))
                              }
                            >
                              {s.role} · {s.title} {opened ? "▾" : "▸"}
                            </button>
                            {opened && (
                              <>
                                <p>{s.content}</p>
                                <ul>
                                  {(s.items || []).map((it) => (
                                    <li key={it}>{it}</li>
                                  ))}
                                </ul>
                              </>
                            )}
                          </div>
                        ),
                      };
                    })}
                  />
                </>
              )}

              {inv?.report && (
                <>
                  <Divider plain orientation="left">
                    可疑交易报告草稿 · 非报送报文
                  </Divider>
                  <ReportText text={inv.report.full_text} issues={inv.fact_issues} onSelect={selectEvidence} />
                  <Input.TextArea
                    rows={2}
                    style={{ marginTop: 10 }}
                    placeholder="调查员意见（修改说明 / 驳回原因）"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  <div className="actions">
                    <Button type="primary" disabled={!inv.can_sign} onClick={() => onDecide("confirm")}>
                      签发结论
                    </Button>
                    <Button onClick={() => onDecide("modify")}>修改后采纳</Button>
                    <Button danger onClick={() => onDecide("reject")}>
                      驳回重查
                    </Button>
                    <Button
                      onClick={() => downloadExport(current).catch((e) => message.error(e.message))}
                    >
                      导出底稿
                    </Button>
                  </div>
                  {!inv.can_sign && (
                    <div className="hint">事实回查未通过：不能「签发结论」。可填写修改说明后「修改后采纳」，或驳回重查。</div>
                  )}
                  <div className="hint">签发只记录人工处置，系统不会向监测中心自动报送。</div>
                </>
              )}
            </div>
          )}
        </main>

        <aside className={`col${showTheater ? " is-waiting" : ""}`}>
          <div className="col-title">
            <h3>证据与关联</h3>
            {selected ? (
              <Button type="link" size="small" onClick={() => setSelected("")}>
                清除筛选
              </Button>
            ) : (
              <span className="hint">点击编号或图谱节点回溯</span>
            )}
          </div>
          {inv ? (
            <>
              <Graph key={showTheater ? "pending" : current} graph={inv.graph} selected={selected} onSelect={selectEvidence} />
              <EvidenceLists graph={inv.evidence_graph} claims={inv.claims} onSelect={selectEvidence} />
              <Divider plain orientation="left">
                制度与类型学
              </Divider>
              {(inv.kb_hits || []).length === 0 ? (
                <div className="hint">本轮未命中知识库。</div>
              ) : (
                (inv.kb_hits || []).map((h) => (
                  <div
                    key={h.id}
                    id={`ev-${h.id}`}
                    className={`ev ${selected === h.id ? "active" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectEvidence(h.id)}
                  >
                    <code>{h.id}</code>
                    <Tag style={{ marginLeft: 6 }}>{h.kind_label}</Tag>
                    <div style={{ fontWeight: 650, margin: "4px 0 2px" }}>{h.title}</div>
                    <div className="hint" style={{ margin: "0 0 4px" }}>
                      {h.source}
                    </div>
                    <div>{h.snippet}</div>
                  </div>
                ))
              )}
              <Divider plain orientation="left">
                交易流水{selected ? "（已筛选）" : ""}
              </Divider>
              <Table
                size="small"
                pagination={{ pageSize: 8, hideOnSinglePage: true, size: "small" }}
                dataSource={txRows}
                scroll={{ x: true }}
                onRow={(row) => ({
                  id: `ev-${row.id}`,
                  onClick: () => selectEvidence(row.id),
                })}
                rowClassName={(row) => (row.id === selected ? "ant-table-row-selected" : "")}
                columns={[
                  {
                    title: "时间",
                    dataIndex: "occurred_at",
                    width: 88,
                    render: (v) => (v ? String(v).slice(5, 16) : "—"),
                  },
                  { title: "编号", dataIndex: "id", width: 108, render: (v) => <code>{v}</code> },
                  { title: "渠道", dataIndex: "channel", width: 72, ellipsis: true },
                  {
                    title: "金额",
                    dataIndex: "amount",
                    width: 88,
                    align: "right",
                    render: (v) => (v == null ? "—" : yuan(v)),
                  },
                ]}
              />
              <Divider plain orientation="left">
                操作审计
              </Divider>
              {(detail?.audit || [])
                .filter((x) => x.action !== "tool")
                .slice(-6)
                .map((x) => {
                  const line = auditText(x);
                  return (
                    <div className="ev" key={x.id} style={{ cursor: "default" }}>
                      <code>{line.title}</code>
                      {line.time ? <span className="hint" style={{ margin: "0 0 0 8px" }}>{line.time}</span> : null}
                      <div>{line.detail}</div>
                    </div>
                  );
                })}
            </>
          ) : (
            <div className="hint">生成草稿后，这里会显示一度对手方、知识库引用、流水和审计。</div>
          )}
        </aside>
      </div>
      </div>
      <footer className="footer">
        <span>内部演示系统　合成数据　不得当作真实监管结论　Agent 建议须人工签发</span>
        <span>
          队列 {metrics?.alerts ?? "—"}　模板精标 {metrics?.labeled ?? "—"}　草稿 {metrics?.drafts ?? "—"}　已签{" "}
          {metrics?.signed ?? "—"}
          {feedback?.rates
            ? `　采纳率 ${Math.round((feedback.rates.confirm || 0) * 100)}%`
            : ""}
        </span>
      </footer>
    </div>
  );
}
