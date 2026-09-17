import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Divider,
  Drawer,
  Form,
  Input,
  Modal,
  Switch,
  Table,
  Timeline,
  Tooltip,
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
  fetchKnowledgeDoc,
  getDemoToken,
  getStoredUser,
  login,
  logout,
  runInvestigate,
  streamInvestigate,
  shouldFallbackInvestigate,
  setDemoToken,
} from "./api";
import BrandLogo from "./BrandLogo.jsx";
import { CounterfactualBox, CustomerCard, EvidenceLists, EvidenceSufficiencyPanel, JudgePanel, RejectedClaims, RegulationBox, RiskFactors, SupplementChecklist, TxTimeline, VerifiedClaims } from "./CasePanels.jsx";
import ContestCoach from "./ContestCoach.jsx";
import Graph from "./Graph.jsx";
import { InvestigateTheater, usePipelinePlayback } from "./InvestigateFlow.jsx";
import SystemManual from "./SystemManual.jsx";
import {
  displayName,
  isDoneStatus,
  isReviewer,
  isTodoStatus,
  persistLabMode,
  readLabMode,
} from "./workstation.js";

const EMPTY_KEYS = [
  ["比赛演示（案例 L 主线）", "0"],
  ["打开案例 A 排除", "1"],
  ["打开案例 B 拆分", "2"],
  ["打开案例 C 归集", "3"],
  ["打开案例 F 观察", "4"],
  ["打开案例 L 多层", "5"],
  ["打开案例 H 抽数", "6"],
  ["系统说明书", "H"],
  ["开始调查", "选中案件后点按钮"],
];

function WelcomeBrief({ labMode }) {
  if (!labMode) {
    return (
      <div className="welcome">
        <div className="welcome-logo">
          <BrandLogo size={68} />
        </div>
        <div className="welcome-title">循证慧查</div>
        <div className="welcome-subtitle">反洗钱调查工作台 · 从左侧待办领取案件</div>
        <p className="welcome-note">生成草稿后由调查员提交复核，合规岗签发。系统不自动报送。</p>
      </div>
    );
  }
  return (
    <div className="welcome">
      <div className="welcome-letterhead">
        <div className="welcome-logo">
          <BrandLogo size={52} />
        </div>
        <div>
          <div className="welcome-title">循证慧查</div>
          <p className="welcome-unit">合规调查工作台</p>
        </div>
      </div>
<<<<<<< HEAD
      <p className="welcome-subtitle">
        从左侧告警池选定案件。系统只出调查草稿，签发由人工完成。快捷键 0 进入案例 L 演示主线。
      </p>
=======
      <div className="welcome-title">循证慧查</div>
      <div className="welcome-subtitle">实验室 · 快捷键 0 进入比赛演示</div>
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
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

function SignDock({ current, inv, user, note, signed, onNote, onDecide, onLogin, onExport, contestHotAction }) {
  const hasDraft = Boolean(inv?.report);
  const factOk = Boolean(hasDraft && inv.can_sign);
  const blockText = signBlockerText(inv);
  const abstained = reliabilityStance(inv) === "abstain";
  const decision = signed?.human_decision || "";
  const submitted = decision === "submit";
  const finalized = decision === "confirm" || decision === "modify";
  const reviewer = isReviewer(user);
  const investigator = Boolean(user) && !reviewer;
  const canSubmit = Boolean(investigator && hasDraft && !finalized && (factOk || note.trim()) && decision !== "submit");
  const canConfirm = Boolean(reviewer && submitted && factOk && !finalized);
  const canModify = Boolean(reviewer && submitted && !finalized);
  const canReject = Boolean(user && hasDraft && !finalized);
  let status = "先选左侧告警";
  if (current) {
    if (!hasDraft) status = "尚无草稿";
    else if (finalized) status = `${HUMAN[decision]}${signed?.signed_by_name ? ` · ${signed.signed_by_name}` : ""}`;
    else if (submitted) {
      status = reviewer
        ? factOk
          ? "待复核签发"
          : `${blockText}，不能直接同意签发`
        : "已提交，等待复核";
    }
    else if (!user) status = "登录后才能提交或签发";
    else if (reviewer) status = "等待调查员提交复核";
    else if (!factOk) status = abstained
      ? `系统已弃权，${blockText}，提交须填写说明`
      : `${blockText}，提交须填写说明`;
    else status = "待提交复核";
  }
  return (
    <div className="sign-dock" data-contest="sign">
      <Input.TextArea
        id="investigator-note"
        rows={4}
        placeholder="处理意见（提交说明 / 复核意见 / 退回原因）"
        value={note}
        onChange={(e) => onNote(e.target.value)}
        disabled={!current}
      />
      <div className="sign-dock-row">
        <div className="sign-dock-actions">
          {(!user || investigator) && (
            <Button
              type="primary"
              className={contestHotAction === "submit" ? "contest-hot" : undefined}
              disabled={!canSubmit}
              onClick={() => onDecide("submit")}
            >
              提交复核
            </Button>
          )}
          {reviewer && (
            <>
              <Button
                type="primary"
                className={contestHotAction === "confirm" ? "contest-hot" : undefined}
                disabled={!canConfirm}
                onClick={() => onDecide("confirm")}
              >
                同意签发
              </Button>
              <Button disabled={!canModify} onClick={() => onDecide("modify")}>
                修改后签发
              </Button>
            </>
          )}
          <Button danger disabled={!canReject} onClick={() => onDecide("reject")}>
            {reviewer ? "退回调查" : "退回重查"}
          </Button>
          <Button disabled={!hasDraft || !user} onClick={onExport}>
            导出底稿
          </Button>
        </div>
        <span className="sign-dock-status">
          {!user ? (
            <>
              <button type="button" className="sign-dock-link" onClick={onLogin}>
                登录
              </button>
              后才能提交或签发
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
  submit: "已提交复核",
  confirm: "复核同意",
  modify: "修改后签发",
  reject: "已退回",
};

function Chip({ tone = "idle", children }) {
  return <span className={`st-chip ${tone}`}>{children}</span>;
}

const STATUS = {
<<<<<<< HEAD
  pending: { text: "待调查", tone: "idle" },
  investigating: { text: "调查中", tone: "work" },
  closed: { text: "已排除关闭", tone: "ok" },
  monitoring: { text: "持续监测", tone: "watch" },
  ready_to_file: { text: "待复核上报", tone: "risk" },
  modified: { text: "人工已改", tone: "watch" },
=======
  pending: { text: "待调查", color: "default" },
  investigating: { text: "调查中", color: "processing" },
  pending_review: { text: "待复核", color: "warning" },
  closed: { text: "已排除关闭", color: "success" },
  monitoring: { text: "持续监测", color: "warning" },
  ready_to_file: { text: "待报送", color: "error" },
  modified: { text: "复核已改", color: "warning" },
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
};

const CONC = {
  exclude: "排除",
  observe: "观察",
  suggest_report: "建议上报",
};

const AUDIT_TITLE = {
  investigate: "生成草稿",
  decide: "人工签发",
  validator: "证据校验",
  checklist: "写入补证",
  export: "导出底稿",
};

<<<<<<< HEAD
const TOOL_LABEL = {
  get_alert: "告警",
  get_customer: "客户资料",
  get_accounts: "账户",
  get_transactions: "交易流水",
  get_timeline: "交易时序",
  get_graph: "资金图谱",
  get_related_accounts: "关联账户",
  get_baseline: "行业基线",
  check_watchlist: "关注名单",
  search_knowledge: "制度",
  search_regulation: "法规",
};

function isToolAudit(x) {
  return x?.actor === "tool" || String(x?.action || "").startsWith("tool");
}

function parseAuditJson(detail) {
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function uniqueLookups(logs) {
  const seen = [];
  for (const x of logs || []) {
    if (!isToolAudit(x)) continue;
    const name = String(x.action || "").replace(/^tool:/, "");
    const label = TOOL_LABEL[name];
    if (label && !seen.includes(label)) seen.push(label);
  }
  return seen;
}

const TOKEN_SPLIT = /(EV-[A-Z0-9\-]+|TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|C-[A-Z0-9]+|KB-[A-Z0-9\-]+)/;
const TOKEN_ONE = /^(EV-[A-Z0-9\-]+|TX-[A-Z0-9\-]+|6222-[A-Z0-9\-]+|CASH-\d+|C-[A-Z0-9]+|KB-[A-Z0-9\-]+)$/;
=======
import { collectSignBlockers, reliabilityStance, signBlockerText } from "./signBlockers.js";
import { isEvidenceToken, splitEvidenceParts } from "./evidenceTokens.js";
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9

const DEMOS = [
  { id: "ALT-A-20260910", key: "1", label: "案例 A 排除" },
  { id: "ALT-B-20260910", key: "2", label: "案例 B 拆分" },
  { id: "ALT-C-20260910", key: "3", label: "案例 C 归集" },
  { id: "ALT-F-20260910", key: "4", label: "案例 F 观察" },
  { id: "ALT-L-20260910", key: "5", label: "案例 L 多层" },
  { id: "ALT-H-20260910", key: "6", label: "案例 H 抽数" },
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

function auditText(x, lookups) {
  const j = parseAuditJson(x.detail) || {};
  const actor = x.actor === "agent" || x.actor === "tool" ? "系统" : x.actor || "调查员";
  const time = x.created_at || "";

  if (x.action === "investigate") {
    const hit = String(j.summary || "").match(/建议结论「([^」]+)」/);
    const conclusion = hit?.[1] || "";
    const flags = [];
    if (j.challenger_enabled === false) flags.push("未开慧查agent");
    if (j.experiment_mode) flags.push("实验模式");
    if (/幻觉演示开启/.test(j.summary || "")) flags.push("幻觉演示");
    return {
      title: AUDIT_TITLE.investigate,
      actor,
      time,
      detail: [conclusion ? `建议${conclusion}` : "已写出调查草稿", ...flags].join("。"),
      extra: lookups?.length ? `查阅 ${lookups.join("、")}` : "",
    };
  }
  if (x.action === "validator") {
    return {
      title: AUDIT_TITLE.validator,
      actor: "系统",
      time,
      detail: "拦截了无效引用，草稿不能直接签发",
    };
  }
  if (x.action === "checklist") {
    const n = Array.isArray(j.item_ids) ? j.item_ids.length : 0;
    return {
      title: AUDIT_TITLE.checklist,
      actor,
      time,
      detail: n ? `把 ${n} 条待补材料写入备注` : "已写入补证备注",
    };
  }
  if (x.action === "decide") {
    const decision = HUMAN[j.human_decision] || j.summary || "已记录";
    const note = String(j.summary || "").includes("：") ? String(j.summary).split("：").slice(1).join("：") : "";
    return {
      title: AUDIT_TITLE.decide,
      actor,
      time,
      detail: note ? `${decision}：${note}` : decision,
    };
  }
  if (x.action === "export") {
    return {
      title: AUDIT_TITLE.export,
      actor,
      time,
      detail: "导出调查底稿，不是报送报文",
    };
  }
  return {
    title: AUDIT_TITLE[x.action] || "其他记录",
    actor,
    time,
    detail: j.summary || "",
  };
}

function ReportText({ text, issues, onSelect }) {
  const bad = new Set((issues || []).map((x) => x.token));
  const parts = splitEvidenceParts(text);
  return (
    <div className="report-box">
      {parts.map((p, i) => {
        if (!p) return null;
        if (bad.has(p)) return <mark key={i}>{p}</mark>;
        if (isEvidenceToken(p)) {
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

function DecisionComparison({ judge, baseline, guardrails, label, ablation, contestHot, reliability }) {
  if (!baseline) return null;
  const same = baseline.conclusion === guardrails?.final_conclusion;
  const abstained = !ablation && reliability?.stance === "abstain";
  return (
    <div className={`score-break${contestHot ? " contest-hot" : ""}`} data-contest="guardrail">
      <div className="score-break-hd">
        判断来源对照
        <b className={conclusionTone(label)}>{label}</b>
      </div>
      <ul>
        <li><span>规则对照</span><em>{CONC[baseline.conclusion] || baseline.conclusion} · {Number(baseline.score ?? 0).toFixed(2)}</em></li>
        <li><span>AI 倾向档</span><em>{ablation ? "未启用" : CONC[judge?.disposition] || judge?.disposition || "—"}</em></li>
        <li><span>系统可靠性</span><em>{ablation ? "—" : abstained ? "弃权" : "可签发倾向"}</em></li>
        <li><span>政策护栏后</span><em>{label}</em></li>
        <li><span>AI 自评把握度</span><em>{ablation ? "—" : Number(judge?.confidence ?? 0).toFixed(2)}</em></li>
      </ul>
      <div className="hint" style={{ margin: "6px 0 0" }}>
        {ablation
          ? "本案为慧查agent 关闭后的消融结果，仅展示规则对照。"
          : abstained
            ? `系统已弃权：上列为 AI 倾向档，不可直接签发。${reliability?.note || ""}`
          : same
            ? "AI 与规则对照一致，没有加权合成。把握度是「对结论有多确定」，不是风险高低。"
            : "AI 与规则对照存在分歧，须由调查员结合引用证据裁决。把握度不是风险分。"}
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
  if (label === "继续观察" || label === "观察") return "watch";
  return "risk";
}

function formatCount(n) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("zh-CN");
}

function usageTokens(blob) {
  if (!blob || typeof blob !== "object") return 0;
  const total = Number(blob.total_tokens);
  if (Number.isFinite(total)) return Math.max(0, total);
  const prompt = Number(blob.prompt_tokens || 0);
  const completion = Number(blob.completion_tokens || 0);
  return Math.max(0, (Number.isFinite(prompt) ? prompt : 0) + (Number.isFinite(completion) ? completion : 0));
}

function investigationTokens(inv) {
  if (!inv) return null;
  if (inv.comparison?.tokens != null && inv.comparison.tokens !== "") {
    const n = Number(inv.comparison.tokens);
    if (Number.isFinite(n)) return n;
  }
  const usage = inv.llm?.usage || {};
  const nested = usageTokens(usage.judge) + usageTokens(usage.reporter);
  if (nested) return nested;
  if (usage.total_tokens != null) return usageTokens(usage);
  return (inv.trace || []).reduce((sum, row) => sum + Number(row?.tokens || 0), 0);
}

function MetricBoard({ metrics, feedback }) {
  const quality = metrics?.quality || {};
  const decided = feedback?.decisions
    ? feedback.decisions.confirm + feedback.decisions.modify + feedback.decisions.reject
    : 0;
  const cards = [
    ["证据契约", quality.evidence_contract_pass_rate == null ? "—" : `${Math.round(quality.evidence_contract_pass_rate * 100)}%`, `${quality.evidence_contract_checked || 0} 次校验`],
    ["拦截无效 Claim", quality.rejected_claims ?? "—", "伪造/跨案/谓词失败"],
    ["事实回查阻断", quality.fact_check_blocked ?? "—", "阻止直接签发"],
    ["平均调查耗时", quality.avg_investigation_ms == null ? "—" : `${quality.avg_investigation_ms} ms`, "从调查开始到草稿"],
    ["消耗 Token", metrics?.tokens == null ? "—" : formatCount(metrics.tokens), "Judge + Reporter 合计"],
    ["人工采纳率", decided ? `${Math.round((feedback.decisions.confirm / decided) * 100)}%` : "—", decided ? `${decided} 次已处置` : "尚无人工样本"],
  ];
  return (
    <section className="metric-board" aria-label="系统成效指标">
      <div className="metric-board-hd">
        <b>系统成效</b>
        <em>合成样本 · 非生产准确率</em>
      </div>
      <dl className="metric-ledger">
        {cards.map(([label, value, note]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <strong>{value}</strong>
              <small>{note}</small>
            </dd>
          </div>
        ))}
      </dl>
      <div className="metric-foot">
<<<<<<< HEAD
        草稿 {metrics?.drafts ?? "—"}　校验 {quality.audited_validations ?? "—"}　签发 {quality.human_decisions ?? "—"}
=======
        已记录 {metrics?.drafts ?? "—"} 份调查草稿 · 消耗 Token {formatCount(metrics?.tokens)} · 审计校验 {quality.audited_validations ?? "—"} 次 · 人工处置 {quality.human_decisions ?? "—"} 次
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
      </div>
    </section>
  );
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
  const [queueKind, setQueueKind] = useState(() => (readLabMode() ? "demo" : "todo"));
  const [labMode, setLabMode] = useState(() => readLabMode());
  const [q, setQ] = useState("");
  const [clock, setClock] = useState(nowText());
  const [offline, setOffline] = useState(false);
  const [llmOff, setLlmOff] = useState(false);
  const [healthInfo, setHealthInfo] = useState(null);
  const [needsToken, setNeedsToken] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [invError, setInvError] = useState(false);
  const [user, setUser] = useState(() => getStoredUser());
  const [loginOpen, setLoginOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [demoAccounts, setDemoAccounts] = useState([]);
  const [loginForm] = Form.useForm();
  const [checklist, setChecklist] = useState(null);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [checklistWriting, setChecklistWriting] = useState(false);
  const [kbArticle, setKbArticle] = useState(null);
  const [kbLoading, setKbLoading] = useState(false);
  const [contestMode, setContestMode] = useState(false);
  const [contestStep, setContestStep] = useState("draft");
  const [stageHint, setStageHint] = useState("");
  const openSeq = useRef(0);
  const startContestRef = useRef(null);
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
    setKbArticle(null);
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
      if (e.key === "h" || e.key === "H") {
        setManualOpen((v) => !v);
        return;
      }
      if (!readLabMode()) return;
      if (e.key === "0") {
        startContestRef.current?.();
        return;
      }
      const hit = DEMOS.find((d) => d.key === e.key);
      if (hit) open(hit.id).catch((err) => message.error(err.message));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (playback.phase === "done") {
      message.success("调查草稿已生成，待提交复核");
    }
  }, [playback.phase]);

  async function onInvestigate(id = current) {
    if (!id || loading) return;
    setCurrent(id);
    if (id && labMode && DEMOS.some((d) => d.id === id)) setQueueKind("demo");
    setInvError(false);
    setLoading(true);
    setStageHint("正在调查…");
    open(id).catch(() => {});
    const opts = {
      useChallenger: experimentMode ? currentChallengerEnabled : true,
      injectHallucination,
      experimentMode,
    };
    const stageLabels = {
      Planner: "规划调查计划…",
      Collector: "归集证据…",
      Privacy: "进模脱敏…",
      Analyst: "提取事实指标…",
      Judge: "Judge 生成建议中…",
      Skeptic: "引用校验与反事实…",
      PolicyGuardrail: "政策护栏检查…",
      Reporter: "生成调查底稿…",
    };
    try {
      try {
        await streamInvestigate(id, opts, (ev) => {
          if (ev?.status === "started" && ev.role && ev.role !== "Assemble") {
            setStageHint(stageLabels[ev.role] || `${ev.role} 进行中…`);
          }
        });
      } catch (e) {
        if (!shouldFallbackInvestigate(e)) throw e;
        await runInvestigate(id, opts);
      }
      await open(id);
      await loadList();
      if (contestMode) setContestStep("evidence");
    } catch (e) {
      setInvError(true);
      message.error(e.message || "调查失败");
    } finally {
      setLoading(false);
      setStageHint("");
    }
  }

  async function onDecide(decision) {
    if (!current) return;
    if (!user) {
      message.warning("请先登录后再提交或签发");
      setLoginOpen(true);
      return;
    }
    try {
      await decide(current, decision, note);
      await open(current);
      await loadList();
      if (!labMode) {
        if (decision === "submit" && !isReviewer(user)) setQueueKind("done");
        if ((decision === "confirm" || decision === "modify") && isReviewer(user)) setQueueKind("done");
        if (decision === "reject") setQueueKind("todo");
      }
      const done = { submit: "已提交复核", confirm: "复核意见已写入审计", modify: "修改后签发已记录", reject: "已退回" };
      message.success(done[decision] || `处置意见已由 ${user.name} 写入审计`);
      if (contestMode) setContestStep("sign");
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

  async function onSwitchDemoUser() {
    const targetId = user?.staff_id === "002183" ? "002201" : "002183";
    setLoginLoading(true);
    try {
      const data = await login(targetId, "aml123");
      setUser(data.user);
      message.success(`已切换为${data.user.name}`);
      loadList().catch(() => {});
    } catch (e) {
      loginForm.setFieldsValue({ staff_id: targetId, password: "aml123" });
      setLoginOpen(true);
      message.error(e.message);
    } finally {
      setLoginLoading(false);
    }
  }

  function setLab(on) {
    persistLabMode(on);
    setLabMode(on);
    setContestMode(false);
    setExperimentMode(false);
    setInjectHallucination(false);
    setQueueKind(on ? "demo" : "todo");
  }

  async function startContest() {
    setContestMode(true);
    setContestStep("draft");
    setExperimentMode(false);
    setInjectHallucination(false);
    setCurrentChallengerEnabled(true);
    setQueueKind("demo");
    try {
      await open("ALT-L-20260910");
      message.success("比赛演示已锁定案例 L。按条带三步走。");
    } catch (e) {
      message.error(e.message);
    }
  }
  startContestRef.current = startContest;

  useEffect(() => {
    if (contestMode && inv && contestStep === "draft") {
      setContestStep("evidence");
    }
  }, [contestMode, inv, contestStep]);

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
    if (contestMode && contestStep === "evidence" && resolved) {
      setContestStep("guardrail");
    }
    if (String(resolved || "").startsWith("KB-")) {
      openKnowledge(resolved);
      return;
    }
    requestAnimationFrame(() => {
      const el = document.getElementById(`ev-${resolved}`) || document.getElementById(`ev-${id}`);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  async function openKnowledge(id) {
    const kid = String(id || "").trim();
    if (!kid.startsWith("KB-")) return;
    const local = (inv?.kb_hits || []).find((h) => h.id === kid);
    setSelected(kid);
    setKbArticle(
      local
        ? { ...local, body: local.body || local.snippet || "" }
        : { id: kid, title: kid },
    );
    requestAnimationFrame(() => {
      document.getElementById(`ev-${kid}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    setKbLoading(true);
    try {
      const full = await fetchKnowledgeDoc(kid);
      setKbArticle(full);
    } catch (e) {
      if (!local?.body && !local?.snippet) {
        message.error(e.message);
        setKbArticle(null);
      }
    } finally {
      setKbLoading(false);
    }
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
  const todoCount = alerts.filter((a) => isTodoStatus(a.status, user)).length;
  const doneCount = alerts.filter((a) => isDoneStatus(a.status, user)).length;
  const queue = alerts
    .filter((a) => {
      if (labMode) return queueKind === "demo" ? Boolean(a.demo_tag) : !a.demo_tag;
      return queueKind === "done" ? isDoneStatus(a.status, user) : isTodoStatus(a.status, user);
    })
    .filter((a) => !q || `${a.title}${a.customer_name}${a.alert_type}${a.id}${a.case_no || ""}`.includes(q));

  return (
    <div className={`app${contestMode ? " is-contest" : ""}`}>
      <header className="topbar">
        <div className="brand">
          <BrandLogo size={36} />
          <div className="brand-text">
            <div className="brand-title-row">
              <strong>循证慧查</strong>
<<<<<<< HEAD
              <span className="brand-unit">合规调查</span>
            </div>
            <span>告警池之后的调查与底稿</span>
=======
              {labMode ? <span className="brand-tag">实验室</span> : <span className="brand-tag">调查工作台</span>}
            </div>
            <span>{labMode ? "实验室 · 快捷键 0 进入比赛演示" : "反洗钱调查工作台 · 调查员提交 / 复核岗签发"}</span>
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
          </div>
        </div>
        <div className="staff">
          <span className="env-chip">演示环境 合成数据</span>
          <span className="top-clock">{clock}</span>
          {labMode && (
            <Tooltip title="锁定案例 L 主线，按 H 打开说明书">
              <button type="button" className="ghost-btn primary" onClick={() => startContest()}>
                比赛演示
              </button>
            </Tooltip>
          )}
          <Tooltip title="按 H 也可打开">
            <button type="button" className="ghost-btn manual-btn" onClick={() => setManualOpen(true)}>
              系统说明书
            </button>
          </Tooltip>
          {contestMode && (
            <button
              type="button"
              className="ghost-btn"
              onClick={onSwitchDemoUser}
              disabled={loginLoading}
              title="复用演示登录，口令 aml123"
            >
              切换陈析 / 李审
            </button>
          )}
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
          <button
            type="button"
            className={`ghost-btn lab-toggle${labMode ? " on" : ""}`}
            onClick={() => setLab(!labMode)}
            title={labMode ? "回到调查工作台" : "打开比赛与实验开关"}
          >
            {labMode ? "退出实验室" : "实验室"}
          </button>
        </div>
      </header>

      <SystemManual open={manualOpen} onClose={() => setManualOpen(false)} health={healthInfo} />

      <div className="toolbar-stack">
      {labMode && (
      <>
      <div className="toolbar">
        <span className={`ch-policy ${experimentMode ? "lab" : "on"}`}>
          {experimentMode ? "实验模式：用于慧查agent 消融实验" : "慧查agent · 已启用"}
        </span>
        <label title="仅影响下一次重跑，不会改写已打开的历史草稿">
          慧查agent
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
        <span className="hint toolbar-keys">
          <kbd>0</kbd> 比赛演示　<kbd>1</kbd>–<kbd>6</kbd> 历史案　<kbd>H</kbd> 说明书
        </span>
      </div>
      {contestMode && (
        <ContestCoach
          step={contestStep}
          hasDraft={Boolean(inv)}
          selected={selected}
          user={user}
          signed={detail}
          llmOff={llmOff}
          onStep={setContestStep}
          onInvestigate={() => onInvestigate("ALT-L-20260910")}
          onHallucination={() => {
            setExperimentMode(true);
            setInjectHallucination(true);
            setContestStep("guardrail");
            message.info("已打开幻觉演示。请重跑，指出 6222-FAKE-9999 标红且不可签发。");
          }}
          onAblation={() => {
            setExperimentMode(true);
            setCurrentChallengerEnabled(false);
            setInjectHallucination(false);
            message.info("下次重跑将关闭慧查agent，只保留规则对照。");
          }}
          onExit={() => setContestMode(false)}
        />
      )}
      </>
      )}
      </div>

      <Modal
<<<<<<< HEAD
        className="desk-modal"
        title="调查员登录"
=======
        title="登录工作台"
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
        open={loginOpen}
        onCancel={() => setLoginOpen(false)}
        footer={null}
        destroyOnClose
        width={420}
      >
        <p className="hint" style={{ marginTop: 0 }}>
          作业分岗：调查员提交复核，合规岗签发。口令均为 <code>aml123</code>。
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
          message="未配置模型密钥"
          description="慧查agent / Reporter 需要 DEEPSEEK_API_KEY、DASHSCOPE_API_KEY 或 ZHIPU_API_KEY。也可设 HUICHA_LLM_STUB=1 走内置 stub。"
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
      <div className="layout">
        <aside className="col">
          <div className="col-title">
<<<<<<< HEAD
            <h3>待办告警</h3>
            <Chip>{queueKind === "demo" ? demoCount : normalCount} 条</Chip>
=======
            <h3>{labMode ? "待办告警" : "我的待办"}</h3>
            <Tag>{labMode ? (queueKind === "demo" ? demoCount : normalCount) : todoCount} 条</Tag>
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
          </div>
          <div
            className={`queue-filter${(labMode ? queueKind === "normal" : queueKind === "done") ? " is-right" : ""}`}
            role="tablist"
            aria-label="告警筛选"
          >
            <i className="queue-filter-thumb" aria-hidden="true" />
            {labMode ? (
              <>
                <button type="button" role="tab" aria-selected={queueKind === "demo"} className={queueKind === "demo" ? "on" : ""} onClick={() => setQueueKind("demo")}>
                  示例 <em>{demoCount}</em>
                </button>
                <button type="button" role="tab" aria-selected={queueKind === "normal"} className={queueKind === "normal" ? "on" : ""} onClick={() => setQueueKind("normal")}>
                  正常数据 <em>{normalCount}</em>
                </button>
              </>
            ) : (
              <>
                <button type="button" role="tab" aria-selected={queueKind !== "done"} className={queueKind !== "done" ? "on" : ""} onClick={() => setQueueKind("todo")}>
                  待办 <em>{todoCount}</em>
                </button>
                <button type="button" role="tab" aria-selected={queueKind === "done"} className={queueKind === "done" ? "on" : ""} onClick={() => setQueueKind("done")}>
                  已办 <em>{doneCount}</em>
                </button>
              </>
            )}
          </div>
          <div className="hint">
            {labMode
              ? queueKind === "demo"
                ? "路演示例案，带 A/B/C/F/L 标签。"
                : "其余合成告警，不是路演脚本。"
              : "调查员提交后进入已办；合规岗待办只看待复核件。系统不自动报送。"}
          </div>
          {labMode && feedback && feedback.decisions && (
            <div className="hint" style={{ marginBottom: 8 }}>
              反馈闭环：采纳 {feedback.decisions.confirm} · 修改 {feedback.decisions.modify} · 驳回{" "}
              {feedback.decisions.reject}
              {feedback.decisions.submit ? ` · 待复核 ${feedback.decisions.submit}` : ""}
              {metrics?.labeled ? ` · 模板精标 ${metrics.labeled}` : ""}
            </div>
          )}
          {labMode && !contestMode && <MetricBoard metrics={metrics} feedback={feedback} />}
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
<<<<<<< HEAD
                  {a.demo_tag ? <span className="demo-stamp">{a.demo_tag}</span> : null}
                  {a.title}
                </div>
                <div className="m">
                  <span className="q-who">{a.customer_name}</span>
                  <span className="q-amt">{yuan(a.amount)}</span>
                </div>
                <div className="q-flags">
                  {a.conclusion ? (
                    <Chip tone={conclusionTone(CONC[a.conclusion] || a.conclusion)}>
                      {CONC[a.conclusion] || a.conclusion}
                    </Chip>
                  ) : null}
                  <Chip tone={st.tone}>{st.text}</Chip>
=======
                  <code className="case-no">{a.case_no || a.id}</code>
                  {labMode && a.demo_tag ? (
                    <Tag color="red" style={{ marginRight: 6 }}>
                      {a.demo_tag}
                    </Tag>
                  ) : null}
                  {a.title}
                </div>
                <div className="m">
                  <span>
                    {displayName(a.customer_name)} · {yuan(a.amount)}
                    {a.account_masked ? ` · ${a.account_masked}` : ""}
                  </span>
                  <span className="queue-tags">
                    {a.conclusion ? <Tag>{CONC[a.conclusion] || a.conclusion}</Tag> : null}
                    <Tag color={st.color}>{st.text}</Tag>
                  </span>
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
                </div>
              </div>
            );
          })}
        </aside>

        <main className={`col is-stage${!current ? " is-welcome" : ""}`}>
          <div className="stage-body">
          {current && detail?.alert && (
            <div className="dossier-hd">
              <div className="dossier-hd-main">
                <div className="dossier-title">
                  {detail.alert.demo_tag ? <span className="demo-stamp">{detail.alert.demo_tag}</span> : null}
                  <h3>{detail.alert.title}</h3>
                </div>
                <div className="dossier-meta">
                  <span>{detail.alert.alert_type}</span>
                  {inv?.customer?.name ? <span>{inv.customer.name}</span> : null}
                  <span>{yuan(detail.alert.amount)}</span>
                  {detail.alert.created_at ? <span>{String(detail.alert.created_at).slice(0, 10)}</span> : null}
                </div>
              </div>
              <div className="dossier-hd-side">
                <code>{detail.alert.id}</code>
                <Chip tone={(STATUS[detail.alert.status] || STATUS.pending).tone}>
                  {(STATUS[detail.alert.status] || STATUS.pending).text}
                </Chip>
              </div>
            </div>
          )}
          {current && !detail?.alert && (
            <div className="col-title">
              <h3>调查作业</h3>
<<<<<<< HEAD
=======
              {detail?.alert && <span className="hint">{detail.alert.case_no || detail.alert.id}</span>}
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
            </div>
          )}
          {!current && <WelcomeBrief labMode={labMode} />}
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
                  <div className="k">规则对照分</div>
                  <div className="v">{inv ? Number(inv.rule_baseline?.score ?? inv.scoring?.base ?? 0).toFixed(2) : "—"}</div>
                  {inv && (
                    <div className="conf-bar" aria-hidden="true">
                      <i style={{ width: `${Math.max(2, Math.min(98, Number(inv.rule_baseline?.score ?? inv.scoring?.base ?? 0) * 100))}%` }} />
                    </div>
                  )}
                  <div className="hint" style={{ margin: "6px 0 0" }}>
                    {inv
                      ? `<0.35 排除 / <0.55 观察。AI 把握度 ${Number(inv.judge?.confidence ?? inv.confidence ?? 0).toFixed(2)} 是确定程度，不是风险。`
                      : "低于 0.35 为排除档"}
                  </div>
                </div>
                <div className="kpi-card">
                  <div className="k">耗时 / 工具次数</div>
                  <div className="v">
                    {inv?.comparison ? `${inv.comparison.agent_ms} ms · ${inv.comparison.tools_called} 次` : "—"}
                  </div>
                </div>
                <div className="kpi-card">
                  <div className="k">消耗 Token</div>
                  <div className="v">{inv ? formatCount(investigationTokens(inv)) : "—"}</div>
                  {inv?.llm?.usage ? (
                    <div className="hint" style={{ margin: "6px 0 0" }}>
                      Judge {formatCount(usageTokens(inv.llm.usage.judge))} · Reporter {formatCount(usageTokens(inv.llm.usage.reporter))}
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="dossier-actions">
                <Button type="primary" disabled={loading || llmOff} onClick={() => onInvestigate()}>
                  {loading ? stageHint || "调查中…" : inv ? "重新调查" : "开始调查"}
                </Button>
<<<<<<< HEAD
                <div className="dossier-flags">
                  {detail?.human_decision ? (
                    <Chip tone="brass">
                      {HUMAN[detail.human_decision]}
                      {detail.signed_by_name ? ` · ${detail.signed_by_name}` : ""}
                    </Chip>
                  ) : (
                    <Chip>待签发</Chip>
                  )}
                  {!user && <Chip tone="watch">未登录</Chip>}
                  {inv && caseChallengerEnabled === false && <Chip tone="watch">消融结果</Chip>}
                  {inv?.inject_hallucination && <Chip tone="risk">已注入幻觉</Chip>}
                  {experimentMode && (
                    <Chip tone="brass">实验模式 · 下次重跑{currentChallengerEnabled ? "启用" : "关闭"}慧查agent</Chip>
                  )}
                </div>
              </div>
              {inv && (
                <dl className="dossier-sum">
                  <div>
                    <dt>上游来源</dt>
                    <dd>{detail?.alert?.upstream || "—"}</dd>
                  </div>
                  {inv.customer?.summary ? (
                    <div>
                      <dt>客户摘要</dt>
                      <dd>{inv.customer.summary}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>本次生成</dt>
                    <dd>
                      {caseChallengerEnabled ? "慧查agent 已参与" : "未启用慧查agent"}
                      {inv.llm?.model ? `，模型 ${inv.llm.model}` : ""}
                      {inv.comparison
                        ? `，调用工具 ${inv.comparison.tools_called} 次，要素 ${inv.comparison.elements_filled}/${inv.comparison.elements_total}`
                        : ""}
                    </dd>
                  </div>
                  {inv.privacy ? (
                    <div>
                      <dt>进模脱敏</dt>
                      <dd>
                        姓名 {inv.privacy.masked_names ?? 0} 个，账号 {inv.privacy.masked_accounts ?? 0} 个
                        {inv.privacy.egress_calls ? `，出站 ${inv.privacy.egress_calls} 次均已检漏` : ""}
                      </dd>
                    </div>
                  ) : null}
                </dl>
              )}
              {inv && caseChallengerEnabled === false && (
=======
                {detail?.human_decision ? (
                  <>
                    <Tag color="gold">{HUMAN[detail.human_decision]}</Tag>
                    {(detail.signed_by_name || detail.signed_by_id) && (
                      <Tag color="blue">
                        处理人 {detail.signed_by_name}
                        {detail.signed_by_id ? ` · ${detail.signed_by_id}` : ""}
                      </Tag>
                    )}
                  </>
                ) : (
                  <Tag>待提交</Tag>
                )}
                {!user && <Tag color="default">未登录</Tag>}
                {inv && caseChallengerEnabled && labMode && (
                  <>
                    <Tag color="green">慧查agent 已参与本次调查</Tag>
                    <Tag>自评把握度 {Number(inv.judge?.confidence ?? 0).toFixed(2)} · 未校准</Tag>
                  </>
                )}
                {inv && caseChallengerEnabled === false && labMode && (
                  <Tag color="orange">本案为消融结果</Tag>
                )}
                {inv?.inject_hallucination && labMode && <Tag color="red">已注入幻觉</Tag>}
                {inv?.llm?.reporter || inv?.llm?.judge ? (
                  labMode ? <Tag color="blue">{inv.llm.model || "百炼已调用"}</Tag> : null
                ) : null}
                {inv?.privacy && (
                  <Tag color="geekblue">
                    进模脱敏 姓名 {inv.privacy.masked_names ?? 0} · 账号 {inv.privacy.masked_accounts ?? 0}
                    {inv.privacy.egress_calls ? ` · 出站 ${inv.privacy.egress_calls} 次已检漏` : ""}
                  </Tag>
                )}
              </Space>
              <div className="client-box">
                {detail?.alert?.upstream}
                {inv?.customer?.summary ? `。${inv.customer.summary}` : ""}
                {inv?.comparison
                  ? ` 工具 ${inv.comparison.tools_called} 次 · 要素 ${inv.comparison.elements_filled}/${inv.comparison.elements_total} · 证据可回溯。`
                  : ""}
              </div>
              {labMode && (
              <div className="ch-state-strip">
                <span>
                  当前运行策略：
                  {experimentMode
                    ? `实验模式 · 下次重跑 ${currentChallengerEnabled ? "启用" : "关闭"} 慧查agent`
                    : "正常模式 · 下次重跑默认启用慧查agent"}
                </span>
                {inv && (
                  <span>
                    本案历史结果：
                    {caseChallengerEnabled
                      ? "生成时已启用慧查agent"
                      : "生成时未启用（消融结果，不是当前系统关闭）"}
                  </span>
                )}
              </div>
              )}
              {inv && caseChallengerEnabled === false && labMode && (
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="本案为消融结果"
                  description="本案生成时未启用慧查agent，当前只展示规则对照的历史调查结果。顶部开关只代表下一次重跑策略，不会改写这份草稿。"
                />
              )}
              {inv && (
                <div className="viz-row">
                  <DecisionComparison judge={inv.judge} baseline={inv.rule_baseline} guardrails={inv.policy_guardrails} label={inv.conclusion_label} ablation={caseChallengerEnabled === false} contestHot={contestMode && contestStep === "guardrail"} reliability={inv.agent_reliability} />
                  <FlowBars baseline={inv.baseline} />
                </div>
              )}
<<<<<<< HEAD
=======
              {inv?.case_v2 && (
                <div className="client-box">
                  案件 {detail?.alert?.case_no || inv.case_v2.case_id} · 建议 {inv.case_v2.recommendation_label} · 风险 {inv.case_v2.risk_level} · 须复核后报送，系统不自动报送
                </div>
              )}
>>>>>>> bc0b166cf5c3232859d6a930289c51c9f3a0bfb9
              {inv && <JudgePanel judge={inv.judge} baseline={inv.rule_baseline} guardrails={inv.policy_guardrails} validation={inv.judge_validation} onSelect={selectEvidence} contestHot={contestMode && contestStep === "evidence"} />}
              {inv && <VerifiedClaims rows={inv.verified_claims} onSelect={selectEvidence} />}
              {inv && <EvidenceSufficiencyPanel data={inv.evidence_sufficiency} onSelect={selectEvidence} />}
              {inv && <RiskFactors risk={inv.risk} onSelect={selectEvidence} />}
              {inv && <TxTimeline rows={inv.timeline} onSelect={selectEvidence} />}
              {inv && <CounterfactualBox cf={inv.counterfactual} />}
              {inv && <RegulationBox cites={inv.structured_report?.regulation_basis} onSelect={selectEvidence} />}
              {inv && <RejectedClaims rows={inv.rejected_claims} onSelect={selectEvidence} />}
              {inv && !inv.can_sign && (
                <Alert
                  type="error"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={inv.fact_issues?.length ? "事实回查未通过，禁止直接签发" : `${signBlockerText(inv)}，禁止直接同意签发`}
                  description={
                    inv.fact_issues?.length
                      ? inv.fact_issues.map((x) => x.token).join("、")
                      : collectSignBlockers(inv).map((row) => row.message).join("；")
                  }
                />
              )}

              {inv?.steps && (
                <>
                  <Divider plain orientation="left">
                    调查过程
                  </Divider>
                  <Timeline
                    items={inv.steps.map((s) => {
                      const defaultOpen = labMode && ["Analyst", "Judge", "慧查agent", "Skeptic", "Reporter"].includes(s.role);
                      const opened = openSteps[s.role] ?? defaultOpen;
                      const stageTrace = (inv.trace || []).find((t) => t.role === s.role);
                      const stageMs = stageTrace?.elapsed_ms;
                      const stageTok = stageTrace?.tokens;
                      return {
                        color: (s.role === "Judge" || s.role === "慧查agent") && inv.use_challenger === false ? "gray" : "blue",
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
                              {labMode && stageMs != null ? (
                                <span style={{ color: "var(--muted)", fontWeight: 400, marginLeft: 8 }}>
                                  {stageMs} ms{stageTok ? ` · ${formatCount(stageTok)} tok` : ""}
                                </span>
                              ) : null}
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
            contestHotAction={
              contestMode && contestStep === "sign" ? (isReviewer(user) ? "confirm" : "submit") : ""
            }
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
              <Graph
                key={showTheater ? "pending" : current}
                graph={inv.graph}
                selected={selected}
                riskFactors={inv.risk?.factors}
                onSelect={selectEvidence}
                formatYuan={yuan}
              />
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
                    className={`ev kb-hit ${selected === h.id || kbArticle?.id === h.id ? "active" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => openKnowledge(h.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openKnowledge(h.id);
                      }
                    }}
                  >
                    <code>{h.id}</code>
                    <Chip>{h.kind_label}</Chip>
                    {h.article ? <Chip>{h.article}</Chip> : null}
                    <div style={{ fontWeight: 650, margin: "4px 0 2px" }}>{h.title}</div>
                    <div className="hint" style={{ margin: "0 0 4px" }}>
                      {h.source}
                    </div>
                    <div className="kb-preview">{h.snippet || h.body}</div>
                    <div className="kb-open">打开全文</div>
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
              <p className="hint">本案的生成与签发记录。</p>
              {(detail?.audit || [])
                .filter((x) => !isToolAudit(x))
                .slice(-8)
                .map((x) => {
                  const lookups = x.action === "investigate" ? uniqueLookups(detail?.audit) : [];
                  const line = auditText(x, lookups);
                  return (
                    <div className="audit-line" key={x.id}>
                      <div className="audit-hd">
                        <b>{line.title}</b>
                        <span>{line.actor}</span>
                        {line.time ? <span>{line.time}</span> : null}
                      </div>
                      {line.detail ? <p>{line.detail}</p> : null}
                      {line.extra ? <p className="audit-extra">{line.extra}</p> : null}
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
      <Drawer
        title={kbArticle ? `${kbArticle.id} · ${kbArticle.title || "知识库条目"}` : "知识库"}
        placement="right"
        width={640}
        open={Boolean(kbArticle)}
        onClose={() => setKbArticle(null)}
        className="kb-drawer"
      >
        {kbArticle && (
          <article className="kb-article">
            <div className="kb-article-meta">
              {kbArticle.kind_label ? <Chip>{kbArticle.kind_label}</Chip> : null}
              {kbArticle.data_note === "official-statute" ? (
                <Chip tone="navy">官方条款</Chip>
              ) : (
                <Chip>作业转述</Chip>
              )}
              <span>{kbArticle.source || "演示知识库"}</span>
            </div>
            <h4>{kbArticle.title || kbArticle.id}</h4>
            {kbLoading && !kbArticle.body && !kbArticle.snippet ? (
              <p className="hint">正在打开全文…</p>
            ) : (
              <p className="kb-article-body">{kbArticle.body || kbArticle.snippet || "本条没有可展示的正文。"}</p>
            )}
            <dl className="kb-article-dl">
              <div>
                <dt>条款</dt>
                <dd>{kbArticle.article || "—"}</dd>
              </div>
              <div>
                <dt>生效日</dt>
                <dd>{kbArticle.effective_date || "—"}</dd>
              </div>
              <div>
                <dt>版本</dt>
                <dd>{kbArticle.version || "—"}</dd>
              </div>
              <div>
                <dt>编号</dt>
                <dd>
                  <code>{kbArticle.id}</code>
                  {kbArticle.parent_id && kbArticle.parent_id !== kbArticle.id ? (
                    <span className="hint"> · 所属 {kbArticle.parent_id}</span>
                  ) : null}
                </dd>
              </div>
            </dl>
            <p className="kb-article-note">
              {kbArticle.data_note === "official-statute"
                ? "本文为官方公布法律/规章条款，按调查引用分篇收录。签发前请与最新有效文本核对。"
                : "本文为作业口径转述，不是法规全文，签发前须回原文核对。"}
            </p>
          </article>
        )}
      </Drawer>
      <footer className="footer">
        <span>
          {labMode ? (contestMode ? "比赛演示 · 案例 L · 实验室　" : "实验室　") : ""}
          反洗钱调查工作台　合成数据　不自动报送　调查员提交 / 复核岗签发
        </span>
        <span>
          队列 {metrics?.alerts ?? "—"}　草稿 {metrics?.drafts ?? "—"}　已签 {metrics?.signed ?? "—"}　Token {formatCount(metrics?.tokens)}
          {!contestMode && feedback?.rates ? `　签发率 ${Math.round((feedback.rates.confirm || 0) * 100)}%` : ""}
        </span>
      </footer>
    </div>
  );
}
