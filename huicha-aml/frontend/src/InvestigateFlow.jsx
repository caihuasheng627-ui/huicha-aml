import { useEffect, useRef, useState } from "react";

const PIPELINE = [
  {
    id: "planner",
    role: "Planner",
    title: "规划",
    caption: "只规划白名单只读工具",
    dwell: 720,
    linger: false,
    ticks: ["核对告警类型", "生成调查计划", "锁定工具白名单"],
    logs: ["plan_tool_names", "核对 ALLOWED_TOOLS", "写入 InvestigationPlan"],
  },
  {
    id: "collector",
    role: "Collector",
    title: "取数",
    caption: "调取客户、流水、知识库",
    dwell: 980,
    linger: false,
    ticks: ["KYC 与账户", "交易样本", "知识库命中"],
    logs: ["get_customer", "get_transactions", "search_knowledge", "get_graph"],
  },
  {
    id: "analyst",
    role: "Analyst",
    title: "分析",
    caption: "规则因子打底风险",
    dwell: 1100,
    linger: false,
    ticks: ["交易模式", "关联网络", "行为基线", "名单命中"],
    logs: ["analyze_pattern", "analyze_network", "analyze_baseline", "watchlist_hit"],
  },
  {
    id: "challenger",
    role: "Challenger",
    title: "质询",
    caption: "AI反向质询 · 有界反证",
    dwell: 1600,
    linger: false,
    ticks: ["寻找反证", "规则先验", "有界 delta ±0.15"],
    logs: ["rule_prior", "enrich_challenger", "clamp_delta"],
  },
  {
    id: "validator",
    role: "Validator",
    title: "核验",
    caption: "谓词执行，拒绝无证据",
    dwell: 860,
    linger: false,
    ticks: ["证据存在性", "谓词复核", "拒绝越界 Claim"],
    logs: ["filter_challenger_items", "predicate_verified", "reject_unbound"],
  },
  {
    id: "reporter",
    role: "Reporter",
    title: "草稿",
    caption: "要素草稿 + 事实回查",
    dwell: 1200,
    linger: true,
    ticks: ["结构化报告", "事实回查", "禁止自动报送"],
    logs: ["render_report", "enrich_report_reason", "fact_check"],
  },
];

const SIGN_STAGE = {
  id: "human",
  role: "Human",
  title: "人签",
  caption: "调查员做最终决策",
};

const RAIL = [...PIPELINE, SIGN_STAGE];

export function usePipelinePlayback({ running, failed }) {
  const [session, setSession] = useState(0);
  const [index, setIndex] = useState(-1);
  const [phase, setPhase] = useState("idle");
  const [subTick, setSubTick] = useState(0);
  const runningRef = useRef(running);
  const failedRef = useRef(failed);
  runningRef.current = running;
  failedRef.current = failed;

  useEffect(() => {
    if (running) setSession((n) => n + 1);
  }, [running]);

  useEffect(() => {
    if (session === 0) return undefined;
    let i = 0;
    let elapsed = 0;
    let last = Date.now();
    setIndex(0);
    setSubTick(0);
    setPhase("playing");

    const timer = setInterval(() => {
      const now = Date.now();
      const dt = Math.min(100, Math.max(0, now - last));
      last = now;
      setSubTick((n) => n + 1);
      if (failedRef.current) {
        setPhase("error");
        clearInterval(timer);
        return;
      }
      const stage = PIPELINE[i];
      const hold = stage.linger && runningRef.current;
      if (hold) {
        setPhase("holding");
        setIndex(i);
        return;
      }
      elapsed += dt;
      if (elapsed < stage.dwell) {
        setPhase("playing");
        setIndex(i);
        return;
      }
      elapsed = 0;
      if (i >= PIPELINE.length - 1) {
        setIndex(i);
        setPhase("done");
        clearInterval(timer);
        return;
      }
      i += 1;
      setIndex(i);
      setPhase("playing");
    }, 80);

    return () => clearInterval(timer);
  }, [session]);

  function reset() {
    setPhase("idle");
    setIndex(-1);
    setSubTick(0);
  }

  const stage = index >= 0 ? PIPELINE[index] : null;
  const last = Math.max(PIPELINE.length - 1, 1);
  const progress = index < 0 ? 0 : phase === "holding" || phase === "done" ? 1 : Math.min(0.96, (index + 0.45) / last);

  return { index, phase, subTick, stage, progress, reset };
}

function StageNode({ stage, state, compact }) {
  return (
    <div className={`pipe-node is-${state}${compact ? " is-compact" : ""}`}>
      <i className="pipe-dot" aria-hidden="true">
        {state === "done" ? (
          <svg viewBox="0 0 12 12">
            <path d="M2.2 6.2 4.8 8.7 9.8 3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
          </svg>
        ) : state === "now" ? (
          <span className="pipe-pulse" />
        ) : null}
      </i>
      <span className="pipe-name">{compact ? stage.title : stage.role}</span>
      {!compact && <span className="pipe-sub">{stage.title}</span>}
    </div>
  );
}

function nodeState(i, index, phase, complete) {
  if (complete) return "done";
  if (phase === "error" && i === index) return "error";
  if (i < index) return "done";
  if (i === index && (phase === "playing" || phase === "holding" || phase === "error")) return "now";
  if (i === index && phase === "pending") return "pending";
  return "wait";
}

export function PipelineRail({ playback, hasDraft, signed, useChallenger }) {
  const live = playback.phase === "playing" || playback.phase === "holding" || playback.phase === "error";
  let { index, phase } = playback;
  let complete = false;
  if (!live) {
    if (signed) {
      complete = true;
      index = RAIL.length - 1;
      phase = "done";
    } else if (hasDraft) {
      index = RAIL.length - 1;
      phase = "pending";
    }
  }
  const fill = complete ? 1 : index < 0 ? 0 : Math.min(0.92, Math.max(0, index / (RAIL.length - 1)));
  return (
    <div className={`pipeline-rail is-${phase}${complete ? " is-complete" : ""}`} aria-label="调查流水线">
      <div className="pipeline-track">
        <i className="pipeline-fill" style={{ width: `${fill * 100}%` }} />
        {phase === "playing" || phase === "holding" ? <i className="pipeline-scan" /> : null}
      </div>
      <ol className="pipeline-nodes">
        {RAIL.map((stage, i) => {
          const muted = !useChallenger && stage.id === "challenger";
          return (
            <li key={stage.id} className={muted ? "is-muted" : undefined}>
              <StageNode stage={stage} state={nodeState(i, index, phase, complete)} compact />
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function InvestigateTheater({ playback, useChallenger, injectHallucination, onRetry, onBack }) {
  const { index, phase, progress, stage } = playback;
  const current = stage || PIPELINE[0];
  const ticks = current.ticks || [];
  const logs = current.logs || [];
  const feed = [
    ...ticks.map((text) => ({ kind: "tick", text })),
    ...logs.map((text) => ({ kind: "log", text })),
  ];
  const failed = phase === "error";
  const rolling = !failed && phase !== "done";
  const pathFill = failed ? 100 : Math.max(0, Math.min(100, progress * 100));

  return (
    <div className={`theater${failed ? " is-error" : ""}`} role="status" aria-live="polite">
      <div className="theater-hd">
        <strong>{failed ? "调查中断" : "正在生成调查草稿"}</strong>
        <span>{failed ? "本轮未写入签发结论" : "只读工具 · 规则打底 · 人做决策"}</span>
      </div>

      <div className="theater-path" aria-hidden="true">
        <i className="theater-path-line" />
        <i className="theater-path-fill" style={{ width: `${pathFill}%` }} />
        {PIPELINE.map((s, i) => (
          <StageNode
            key={s.id}
            stage={s}
            state={nodeState(i, index, phase, false)}
            compact
          />
        ))}
      </div>

      <div className="theater-now">
        <div className="theater-role">
          <b>{current.role}</b>
          <em>{!useChallenger && current.id === "challenger" ? "本轮已关闭（消融）" : current.caption}</em>
        </div>
        <div className="theater-feed" aria-hidden="true">
          <div key={current.id} className={`theater-feed-track${rolling ? " is-rolling" : ""}`}>
            {(failed ? [{ kind: "log", text: "pipeline_aborted" }] : [...feed, ...feed]).map((item, i) => (
              <div key={`${item.kind}-${item.text}-${i}`} className={`theater-feed-row is-${item.kind}`}>
                {item.kind === "log" ? <code>{item.text}</code> : <span>{item.text}</span>}
              </div>
            ))}
          </div>
        </div>
        {injectHallucination && current.id === "reporter" && (
          <p className="theater-warn">幻觉演示已开：签发将被事实回查拦住</p>
        )}
        {phase === "holding" && <p className="theater-hold">正在等待模型返回草稿…</p>}
      </div>

      {failed && (
        <div className="theater-actions">
          <button type="button" className="theater-btn primary" onClick={onRetry}>
            重新调查
          </button>
          <button type="button" className="theater-btn" onClick={onBack}>
            返回案件
          </button>
        </div>
      )}
    </div>
  );
}
