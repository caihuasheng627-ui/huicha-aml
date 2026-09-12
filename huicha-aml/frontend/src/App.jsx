import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Divider,
  Form,
  Input,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Timeline,
  message,
} from "antd";
import {
  appendChecklist,
  clearSession,
  decide,
  downloadExport,
  fetchAlerts,
  fetchAuthAccounts,
  fetchChecklist,
  fetchDetail,
  fetchFeedback,
  fetchHealth,
  fetchMe,
  fetchMetrics,
  getDemoToken,
  getStoredUser,
  login,
  logout,
  runInvestigate,
  setDemoToken,
} from "./api";
import BrandLogo from "./BrandLogo.jsx";
import { ChallengerPanel, CounterfactualBox, CustomerCard, EvidenceLists, RejectedClaims, RegulationBox, RiskFactors, SupplementChecklist, TxTimeline, VerifiedClaims } from "./CasePanels.jsx";
import Graph from "./Graph.jsx";
import { InvestigateTheater, usePipelinePlayback } from "./InvestigateFlow.jsx";

const EMPTY_KEYS = [
  ["打开案例 A 排除", "1"],
  ["打开案例 B 拆分", "2"],
  ["打开案例 C 归集", "3"],
  ["打开案例 F 观察", "4"],
  ["打开案例 L 多层", "5"],
  ["按当前策略重跑", "选中案件后点按钮"],
];

function WelcomeBrief() {
  return (
    <div className="welcome">
      <div className="welcome-mark" aria-hidden="true">
        循证慧查
      </div>
      <table className="welcome-keys">
        <tbody>
          {EMPTY_KEYS.map(([action, key]) => (
            <tr key={action}>
              <td>{action}</td>
              <td>{key.length === 1 ? <kbd>{key}</kbd> : <span>{key}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SignDock({ current, inv, user, note, signed, onNote, onDecide, onLogin, onExport }) {
  const hasDraft = Boolean(inv?.report);
  const canSign = Boolean(hasDraft && inv.can_sign);
  const status = !current
    ? "先选左侧告警"
    : !hasDraft
      ? "尚无草稿"
      : signed?.human_decision
        ? `${HUMAN[signed.human_decision]}${signed.signed_by_name ? ` · ${signed.signed_by_name}` : ""}`
        : canSign
          ? "待签发"
          : "事实回查未通过，不能签发";
  return (
    <div className="sign-dock">
      <Input.TextArea
        id="investigator-note"
        rows={4}
        placeholder="调查员意见（修改说明 / 驳回原因）"
        value={note}
        onChange={(e) => onNote(e.target.value)}
        disabled={!current}
      />
      <div className="sign-dock-row">
        <div className="sign-dock-actions">
          <Button type="primary" disabled={!canSign} onClick={() => onDecide("confirm")}>
            签发结论
          </Button>
          <Button disabled={!hasDraft} onClick={() => onDecide("modify")}>
            修改后采纳
          </Button>
          <Button danger disabled={!hasDraft} onClick={() => onDecide("reject")}>
            驳回重查
          </Button>
          <Button disabled={!hasDraft} onClick={onExport}>
            导出底稿
          </Button>
        </div>
        <span className="sign-dock-status">
          {!user ? (
            <>
              <button type="button" className="sign-dock-link" onClick={onLogin}>
                登录
              </button>
              后才能签发
            </>
          ) : (
            status
          )}
        </span>
      </div>
    </div>
  );
}

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
  validator: "证据校验",
  checklist: "补证清单",
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
  const actor = x.actor === "agent" ? "系统" : x.actor || "调查员";
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

function ScoreBreakdown({ scoring, label, ablation }) {
  if (!scoring) return null;
  const base = Number(scoring.base ?? 0);
  const prior = Number(scoring.rule_prior ?? 0);
  const delta = Number(scoring.llm_delta ?? 0);
  const raw = Number(scoring.raw ?? base + prior + delta);
  const final = Number(scoring.final ?? 0);
  const floored = Math.abs(raw - final) > 1e-9;
  const suppressed = Boolean(scoring.delta_suppressed);
  const rows = ablation
    ? [
        { k: "规则底分", v: final, abs: true },
        { k: "Challenger", v: 0 },
        { k: "展示分", v: final, abs: true },
      ]
    : [
        { k: "规则底分", v: base, abs: true },
        { k: "规则先验", v: prior },
        { k: "Challenger", v: delta },
        { k: "合成", v: raw },
        { k: "展示分", v: final, abs: true },
      ];
  const pin = Math.max(2, Math.min(98, final * 100));
  return (
    <div className="score-break">
      <div className="score-break-hd">
        可解释风险评分
        <b className={conclusionTone(label)}>{label}</b>
      </div>
      <ul>
        {rows.map((r) => {
          const n = Number(r.v ?? 0);
          return (
            <li key={r.k}>
              <span>{r.k}</span>
              <em className={n < 0 ? "down" : n > 0 && !r.abs ? "up" : ""}>
                {r.abs ? n.toFixed(2) : `${n > 0 ? "+" : ""}${n.toFixed(2)}`}
              </em>
            </li>
          );
        })}
      </ul>
      <div className="hint" style={{ margin: "6px 0 0" }}>
        {suppressed ? "底分加先验已是排除，负向 Challenger 未再叠加。" : ""}
        {floored ? `${suppressed ? " " : ""}合成 ${raw.toFixed(2)} 已夹到展示区间 0.05–0.95。` : ""}
        {!floored && !suppressed ? "Challenger 进分不超过 ±0.15。" : ""}
        {ablation ? " 本案为 Challenger OFF 消融结果。" : ""}
      </div>
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
  const [currentChallengerEnabled, setCurrentChallengerEnabled] = useState(true);
  const [experimentMode, setExperimentMode] = useState(false);
  const [injectHallucination, setInjectHallucination] = useState(false);
  const [selected, setSelected] = useState("");
  const [openSteps, setOpenSteps] = useState({});
  const [queueKind, setQueueKind] = useState("demo");
  const [q, setQ] = useState("");
  const [clock, setClock] = useState(nowText());
  const [offline, setOffline] = useState(false);
  const [llmOff, setLlmOff] = useState(false);
  const [healthInfo, setHealthInfo] = useState(null);
  const [needsToken, setNeedsToken] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [invError, setInvError] = useState(false);
  const [honestyHint, setHonestyHint] = useState(true);
  const [user, setUser] = useState(() => getStoredUser());
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [demoAccounts, setDemoAccounts] = useState([]);
  const [loginForm] = Form.useForm();
  const [checklist, setChecklist] = useState(null);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [checklistWriting, setChecklistWriting] = useState(false);
  const openSeq = useRef(0);
  const inv = detail?.investigation;
  const playback = usePipelinePlayback({ running: loading, failed: invError });
  const showTheater = playback.phase === "playing" || playback.phase === "holding" || playback.phase === "error";
  const caseChallengerEnabled = inv ? inv.case_challenger_enabled !== false && inv.use_challenger !== false : null;
  const nextChallengerEnabled = experimentMode ? currentChallengerEnabled : true;

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
    if (d.investigation) {
      setChecklistLoading(true);
      fetchChecklist(id)
        .then((c) => {
          if (seq !== openSeq.current) return;
          setChecklist(c);
        })
        .catch(() => {
          if (seq !== openSeq.current) return;
          setChecklist(d.investigation.checklist || null);
        })
        .finally(() => {
          if (seq === openSeq.current) setChecklistLoading(false);
        });
    } else {
      setChecklist(null);
    }
  }

  async function onWriteChecklist(itemIds) {
    if (!current || !itemIds?.length) return;
    setChecklistWriting(true);
    try {
      const data = await appendChecklist(current, itemIds);
      setChecklist(data);
      setNote(data.human_note || "");
      message.success(`已将 ${data.appended?.length || itemIds.length} 条写入草稿备注`);
      requestAnimationFrame(() => {
        document.getElementById("investigator-note")?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    } catch (e) {
      message.error(e.message);
    } finally {
      setChecklistWriting(false);
    }
  }

  useEffect(() => {
    loadList().catch((e) => message.error(e.message.includes("调查服务") || e.message.includes("fetch") ? "无法连接调查服务，请先启动后端 8000 端口" : e.message));
    const t = setInterval(() => setClock(nowText()), 1000);
    if (getStoredUser()) {
      fetchMe()
        .then((d) => setUser(d.user))
        .catch(() => {
          clearSession();
          setUser(null);
        });
    }
    fetchAuthAccounts()
      .then((d) => setDemoAccounts(d.accounts || []))
      .catch(() => {});
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

  useEffect(() => {
    if (playback.phase === "done") {
      message.success("调查草稿已生成，待人工签发");
    }
  }, [playback.phase]);

  useEffect(() => {
    if (!honestyHint || !healthInfo?.limitations?.[0]) return undefined;
    const t = setTimeout(() => setHonestyHint(false), 6000);
    return () => clearTimeout(t);
  }, [honestyHint, healthInfo?.limitations?.[0]]);

  async function onInvestigate(id = current) {
    if (!id || loading) return;
    setCurrent(id);
    if (DEMOS.some((d) => d.id === id)) setQueueKind("demo");
    setInvError(false);
    setLoading(true);
    open(id).catch(() => {});
    try {
      await runInvestigate(id, {
        useChallenger: experimentMode ? currentChallengerEnabled : true,
        injectHallucination,
        experimentMode,
      });
      await open(id);
      await loadList();
    } catch (e) {
      setInvError(true);
      message.error(e.message || "调查失败");
    } finally {
      setLoading(false);
    }
  }

  async function onDecide(decision) {
    if (!current) return;
    if (!user) {
      message.warning("请先登录后再签发");
      setLoginOpen(true);
      return;
    }
    try {
      await decide(current, decision, note);
      await open(current);
      await loadList();
      message.success(`处置意见已由 ${user.name} 写入审计`);
    } catch (e) {
      if (String(e.message || "").includes("登录")) {
        clearSession();
        setUser(null);
        setLoginOpen(true);
      }
      message.error(e.message);
    }
  }

  async function onLogin(values) {
    setLoginLoading(true);
    try {
      if (values.demo_token != null) setDemoToken(values.demo_token || "");
      const data = await login(values.staff_id, values.password);
      setUser(data.user);
      setLoginOpen(false);
      loginForm.resetFields(["password"]);
      message.success(`${data.user.name} 已登录`);
      loadList().catch(() => {});
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoginLoading(false);
    }
  }

  async function onLogout() {
    await logout();
    setUser(null);
    message.success("已退出登录");
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

  const demoCount = alerts.filter((a) => a.demo_tag).length;
  const normalCount = alerts.filter((a) => !a.demo_tag).length;
  const queue = alerts
    .filter((a) => (queueKind === "demo" ? Boolean(a.demo_tag) : !a.demo_tag))
    .filter((a) => !q || `${a.title}${a.customer_name}${a.alert_type}${a.id}`.includes(q));

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <BrandLogo />
          <div className="brand-text">
            <strong>循证慧查</strong>
            <span>告警后调查工作台</span>
          </div>
        </div>
        <div className="staff">
          <span className="top-clock">{clock}</span>
          {user ? (
            <div className="user-chip">
              <div className="user-meta">
                <b>{user.name}</b>
                <span>
                  {user.role} · {user.staff_id}
                </span>
              </div>
              <button type="button" className="ghost-btn" onClick={onLogout}>
                退出
              </button>
            </div>
          ) : (
            <button type="button" className="ghost-btn primary" onClick={() => setLoginOpen(true)}>
              登录
            </button>
          )}
        </div>
      </header>

      <div className="toolbar">
        <span className={`ch-policy ${experimentMode ? "lab" : "on"}`}>
          {experimentMode ? "实验模式：用于 Challenger 消融实验" : "AI反向质询 · 已启用"}
        </span>
        <label title="仅影响下一次重跑，不会改写已打开的历史草稿">
          AI反向质询（Challenger）
          <Switch
            size="small"
            checked={nextChallengerEnabled}
            disabled={!experimentMode}
            onChange={setCurrentChallengerEnabled}
          />
        </label>
        {!experimentMode && (
          <span className="hint" style={{ margin: 0 }}>
            正常模式默认启用
          </span>
        )}
        {experimentMode && (
          <span className="hint" style={{ margin: 0 }}>
            下次重跑：{currentChallengerEnabled ? "开" : "关（消融）"}
          </span>
        )}
        <label>
          实验模式
          <Switch
            size="small"
            checked={experimentMode}
            onChange={(on) => {
              setExperimentMode(on);
              if (!on) {
                setCurrentChallengerEnabled(true);
                setInjectHallucination(false);
              }
            }}
          />
        </label>
        {experimentMode && (
          <label>
            幻觉演示
            <Switch size="small" checked={injectHallucination} onChange={setInjectHallucination} />
          </label>
        )}
        <span className="hint" style={{ margin: 0 }}>
          快捷键 1–5 打开历史案（不重跑）；顶部策略只作用于「按当前策略重跑」。签发须登录；AI 不得自动报送。
        </span>
      </div>

      <Modal
        title="调查员登录"
        open={loginOpen}
        onCancel={() => setLoginOpen(false)}
        footer={null}
        destroyOnClose
        width={420}
      >
        <p className="hint" style={{ marginTop: 0 }}>
          演示账号口令均为 <code>aml123</code>。签发结论将绑定当前登录人。
        </p>
        {demoAccounts.length > 0 && (
          <div className="login-accounts">
            {demoAccounts.map((a) => (
              <button
                key={a.staff_id}
                type="button"
                className="login-account"
                onClick={() =>
                  loginForm.setFieldsValue({ staff_id: a.staff_id, password: "aml123" })
                }
              >
                <b>{a.name}</b>
                <span>
                  {a.role} · {a.staff_id}
                </span>
              </button>
            ))}
          </div>
        )}
        <Form
          form={loginForm}
          layout="vertical"
          onFinish={onLogin}
          initialValues={{ staff_id: "002183", demo_token: getDemoToken() }}
        >
          <Form.Item name="staff_id" label="工号" rules={[{ required: true, message: "请输入工号" }]}>
            <Input placeholder="如 002183" autoFocus />
          </Form.Item>
          <Form.Item name="password" label="口令" rules={[{ required: true, message: "请输入口令" }]}>
            <Input.Password placeholder="演示口令" />
          </Form.Item>
          {healthInfo?.auth === "demo_token" && (
            <Form.Item name="demo_token" label="接口演示口令">
              <Input.Password placeholder="X-Huicha-Token" />
            </Form.Item>
          )}
          <Button type="primary" htmlType="submit" block loading={loginLoading}>
            登录
          </Button>
        </Form>
      </Modal>

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
          description={
            <span>
              后端启用了 HUICHA_DEMO_TOKEN。请
              <Button type="link" size="small" style={{ padding: "0 4px" }} onClick={() => setLoginOpen(true)}>
                登录
              </Button>
              并填写接口演示口令。
            </span>
          }
        />
      )}
      {honestyHint && healthInfo?.limitations?.[0] && (
        <Alert
          type="info"
          banner
          showIcon
          closable
          afterClose={() => setHonestyHint(false)}
          message="诚实边界"
          description={`${healthInfo.limitations[0]}；知识库为关键词重叠检索（${healthInfo.kb_retrieval || "keyword-overlap"}），不是语义向量库。`}
        />
      )}

      <div className="layout">
        <aside className="col">
          <div className="col-title">
            <h3>待办告警</h3>
            <Tag>{queueKind === "demo" ? demoCount : normalCount} 条</Tag>
          </div>
          <div className="queue-filter" role="tablist" aria-label="告警筛选">
            <button
              type="button"
              role="tab"
              aria-selected={queueKind === "demo"}
              className={queueKind === "demo" ? "on" : ""}
              onClick={() => setQueueKind("demo")}
            >
              示例 <em>{demoCount}</em>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={queueKind === "normal"}
              className={queueKind === "normal" ? "on" : ""}
              onClick={() => setQueueKind("normal")}
            >
              正常数据 <em>{normalCount}</em>
            </button>
          </div>
          <div className="hint">
            {queueKind === "demo"
              ? "路演示例案，带 A/B/C/F/L 标签。"
              : "其余合成告警，不是路演脚本。"}{" "}
            本台只出草稿，不是监管结论。
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

        <main className={`col is-stage${!current ? " is-welcome" : ""}`}>
          <div className="stage-body">
          {current && (
            <div className="col-title">
              <h3>调查作业</h3>
              {detail?.alert && <span className="hint">{detail.alert.id}</span>}
            </div>
          )}
          {!current && <WelcomeBrief />}
          {current && showTheater && (
            <InvestigateTheater
              playback={playback}
              useChallenger={nextChallengerEnabled}
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
                  <div className="k">可解释风险评分</div>
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
                  <>
                    <Tag color="gold">{HUMAN[detail.human_decision]}</Tag>
                    {(detail.signed_by_name || detail.signed_by_id) && (
                      <Tag color="blue">
                        签发人 {detail.signed_by_name}
                        {detail.signed_by_id ? ` · ${detail.signed_by_id}` : ""}
                      </Tag>
                    )}
                  </>
                ) : (
                  <Tag>待签发</Tag>
                )}
                {!user && <Tag color="default">未登录 · 不可签发</Tag>}
                {inv && caseChallengerEnabled && (
                  <>
                    <Tag color="green">AI反向质询已参与本次调查</Tag>
                    {inv.scoring?.llm_delta != null && (
                      <Tag>
                        模型调整 Δ = {Number(inv.scoring.llm_delta) > 0 ? "+" : ""}
                        {Number(inv.scoring.llm_delta).toFixed(2)}
                      </Tag>
                    )}
                  </>
                )}
                {inv && caseChallengerEnabled === false && (
                  <Tag color="orange">本案为消融结果</Tag>
                )}
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
              <div className="ch-state-strip">
                <span>
                  当前运行策略：
                  {experimentMode
                    ? `实验模式 · 下次重跑 ${currentChallengerEnabled ? "启用" : "关闭"} AI反向质询`
                    : "正常模式 · 下次重跑默认启用 AI反向质询"}
                </span>
                {inv && (
                  <span>
                    本案历史结果：
                    {caseChallengerEnabled
                      ? "生成时已启用 AI反向质询"
                      : "生成时未启用（消融结果，不是当前系统关闭）"}
                  </span>
                )}
              </div>
              {inv && caseChallengerEnabled === false && (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="本案为消融结果"
                  description="本案生成时未启用 AI 反向质询，当前展示的是 Challenger OFF 的历史调查结果。顶部开关只代表下一次重跑策略，不会改写这份草稿。可点「按当前策略重跑」。"
                />
              )}
              {inv && (
                <div className="viz-row">
                  <ScoreBreakdown scoring={inv.scoring} label={inv.conclusion_label} ablation={caseChallengerEnabled === false} />
                  <FlowBars baseline={inv.baseline} />
                </div>
              )}
              {inv?.case_v2 && (
                <div className="client-box">
                  案件 {inv.case_v2.case_id} · 建议 {inv.case_v2.recommendation_label} · 风险 {inv.case_v2.risk_level} ·
                  数据 {inv.data_note || "synthetic"} · Agent 不得自动报送
                </div>
              )}
              {inv && <ChallengerPanel run={inv.challenger_run} onSelect={selectEvidence} />}
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
                  <SupplementChecklist
                    data={checklist || inv.checklist}
                    loading={checklistLoading}
                    writing={checklistWriting}
                    onWrite={onWriteChecklist}
                  />
                </>
              )}
            </div>
          )}
          </div>
          <SignDock
            current={current}
            inv={inv}
            user={user}
            note={note}
            signed={detail}
            onNote={setNote}
            onDecide={onDecide}
            onLogin={() => setLoginOpen(true)}
            onExport={() => downloadExport(current).catch((e) => message.error(e.message))}
          />
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
              <CustomerCard
                customer={inv.customer}
                accountId={detail?.alert?.account_id}
                selected={selected}
                onSelect={selectEvidence}
              />
              <Graph key={showTheater ? "pending" : current} graph={inv.graph} selected={selected} onSelect={selectEvidence} formatYuan={yuan} />
              <EvidenceLists
                graph={inv.evidence_graph}
                claims={inv.claims}
                kbHits={inv.kb_hits}
                ablation={caseChallengerEnabled === false}
                selected={selected}
                onSelect={selectEvidence}
              />
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
