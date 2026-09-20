const STEPS = [
  {
    id: "draft",
    title: "生成草稿",
    talk: "案例 L 已打开。点「开始调查」，不要开实验模式。",
  },
  {
    id: "evidence",
    title: "1 证据闭环",
    talk: "点理由旁的交易编号，右栏应回到对应流水。",
  },
  {
    id: "guardrail",
    title: "2 安全兜底",
    talk: "指判断来源对照里的「政策护栏后」：规则与 AI 不相加，建议上报也不是已报送。",
  },
  {
    id: "sign",
    title: "3 人工负责",
    talk: "用户条「切换调查员 / 复核岗」换岗。当前岗只点高亮按钮：调查员「提交复核」，复核岗「同意签发」。系统不会自动报送。",
  },
];

export default function ContestCoach({
  step,
  hasDraft,
  selected,
  user,
  signed,
  llmOff,
  onStep,
  onInvestigate,
  onHallucination,
  onAblation,
  onExit,
}) {
  const idx = Math.max(0, STEPS.findIndex((s) => s.id === step));
  const current = STEPS[idx] || STEPS[0];
  return (
    <div className="contest-coach" role="status">
      <div className="contest-coach-main">
        <b>比赛演示 · 案例 L</b>
        <ol>
          {STEPS.map((s, i) => (
            <li key={s.id}>
              <button
                type="button"
                className={s.id === current.id ? "on" : ""}
                onClick={() => onStep(s.id)}
              >
                {i === 0 ? "草稿" : s.title.replace(/^\d\s/, "")}
              </button>
            </li>
          ))}
        </ol>
        <p>{current.talk}</p>
        {llmOff && (
          <p className="contest-warn">
            未配置模型。请预热过的案例 L，或后端设 HUICHA_LLM_STUB=1 后重跑。
          </p>
        )}
        {hasDraft && selected ? <p className="contest-ok">已点回 {selected}</p> : null}
        {user && (signed?.human_decision === "confirm" || signed?.human_decision === "modify") ? (
          <p className="contest-ok">
            已签发 · {signed.signed_by_name || user.name} · 不是已报送
          </p>
        ) : user && signed?.human_decision === "submit" ? (
          <p className="contest-ok">已提交复核，请登录复核岗签发</p>
        ) : null}
      </div>
      <div className="contest-coach-actions">
        {!hasDraft && (
          <button type="button" className="contest-primary" onClick={onInvestigate}>
            生成草稿
          </button>
        )}
        <button type="button" onClick={onHallucination}>
          备用：幻觉拦截
        </button>
        <button type="button" onClick={onAblation}>
          备用：关闭慧查agent
        </button>
        <button type="button" onClick={onExit}>
          退出演示条
        </button>
      </div>
    </div>
  );
}
