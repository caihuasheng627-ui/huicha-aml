import { Drawer, Tag } from "antd";
import BrandLogo from "./BrandLogo.jsx";

const STEPS = [
  ["选告警", "左栏「待办告警」按示例 / 正常数据切换，也可按客户名、告警类型或编号搜索。"],
  ["生成草稿", "中栏点「开始调查」。流水线按规划 → 取证 → 指标 → Judge → 核验 → 护栏 → 报告推进，全过程可见。"],
  ["读三方对照", "「判断来源对照」并排给出规则对照、AI Judge 建议和政策护栏后结论。三者不相加，分歧须由人裁决。"],
  ["回溯证据", "点报告里的证据编号、法规依据或图谱节点，右栏会定位到对应流水、客户资料与制度摘录。"],
  ["人工签发", "登录后填写调查员意见，再选「签发结论」「修改后采纳」或「驳回重查」。系统不会自动报送。"],
];

const PANELS = [
  ["左栏", "待办告警队列、筛选与反馈闭环统计。"],
  ["中栏", "案件舞台：指标卡、三方对照、Judge 面板、风险因子、时间线、反事实、法规依据、调查过程、报告草稿与待补证清单。底部是签发区。"],
  ["右栏", "证据与关联：客户 KYC 卡、资金图谱、证据分组、制度与类型学、交易流水和操作审计。"],
];

const CONCLUSIONS = [
  ["排除", "ok", "证据足以说明交易与客户身份、职业或经营特征相符，但仍须写明排除理由。"],
  ["继续观察", "warn", "疑点未排除也未达上报门槛，保留监测。"],
  ["建议上报", "risk", "仅为草稿建议，须调查员签发后再由复核与总部审定流程处理。"],
];

const BLOCKERS = [
  ["事实回查未通过", "报告里出现了本案证据范围之外的账号、金额或编号，签发按钮锁定，须重跑或人工修改。"],
  ["Judge 证据契约未通过", "理由缺引用、引用了工具范围外的编号，或建议上报却没有支持证据，整份 AI 建议作废，只保留规则对照。"],
];

const SWITCHES = [
  ["AI 调查 Judge", "正常模式下默认启用。只影响下一次重跑，不会改写已打开的历史草稿。"],
  ["实验模式", "开启后才能关闭 Judge 做消融对照，用于验证「有无 AI Judge」的差异。"],
  ["幻觉演示", "实验模式专用，故意注入不实表述，用来演示事实回查与签发拦截确实生效。"],
];

const KEYS = [
  ["1 / 2 / 3 / 4 / 5", "打开案例 A 排除、B 拆分、C 归集、F 观察、L 多层（只打开历史草稿，不重跑）。"],
  ["点击编号", "报告、理由、法规、图谱里的编号都可点，用于回溯原始证据。"],
];

export default function SystemManual({ open, onClose, health }) {
  return (
    <Drawer
      title="系统说明书"
      placement="right"
      width={560}
      open={open}
      onClose={onClose}
      className="manual-drawer"
    >
      <div className="manual">
        <div className="manual-hero">
          <BrandLogo size={44} />
          <div>
            <b>循证慧查 · 证据约束的反洗钱调查工作台</b>
            <p>
              上游监测已经出了告警，本台只负责把告警升级为可追溯的案件草稿：AI 负责推理，规则负责边界，证据负责事实，
              <em>人负责最终决策</em>。系统不连接真实银行，不会自动报送。
            </p>
          </div>
        </div>

        <section className="manual-sec">
          <h4>一、五步走完一个案子</h4>
          <ol className="manual-steps">
            {STEPS.map(([name, desc]) => (
              <li key={name}>
                <b>{name}</b>
                <span>{desc}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="manual-sec">
          <h4>二、三栏分别看什么</h4>
          <dl className="manual-dl">
            {PANELS.map(([name, desc]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{desc}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="manual-sec">
          <h4>三、结论三档</h4>
          <ul className="manual-list">
            {CONCLUSIONS.map(([name, tone, desc]) => (
              <li key={name}>
                <b className={tone}>{name}</b>
                <span>{desc}</span>
              </li>
            ))}
          </ul>
          <p className="manual-note">
            「把握度」是模型对自己结论的自评，未经概率校准，不等于风险高低，也不能写成准确率。
          </p>
        </section>

        <section className="manual-sec">
          <h4>四、什么情况下不能签发</h4>
          <ul className="manual-list">
            {BLOCKERS.map(([name, desc]) => (
              <li key={name}>
                <b className="risk">{name}</b>
                <span>{desc}</span>
              </li>
            ))}
          </ul>
          <p className="manual-note">签发须先登录，签发人会写入审计留痕；AI 不得自动报送监测中心。</p>
        </section>

        <section className="manual-sec">
          <h4>五、顶栏策略开关</h4>
          <dl className="manual-dl">
            {SWITCHES.map(([name, desc]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{desc}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="manual-sec">
          <h4>六、快捷操作</h4>
          <dl className="manual-dl">
            {KEYS.map(([name, desc]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{desc}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="manual-sec">
          <h4>七、运行环境</h4>
          <div className="manual-chips">
            <Tag>版本 {health?.version || "—"}</Tag>
            <Tag color={health?.llm && health.llm !== "off" ? "blue" : "red"}>
              模型 {health?.model || health?.llm || "未配置"}
            </Tag>
            <Tag>知识库 {health?.kb_docs ?? "—"} 条</Tag>
            <Tag>检索 {health?.kb_retrieval || "keyword-overlap"}</Tag>
            <Tag color="orange">数据 {health?.data_note || "synthetic"}</Tag>
          </div>
          <p className="manual-note">{health?.stack || "FastAPI + SQLite + React（竞赛原型）"}</p>
        </section>

        <section className="manual-sec">
          <h4>八、诚实边界</h4>
          <ul className="manual-limits">
            {(health?.limitations || []).map((x) => (
              <li key={x}>{x}</li>
            ))}
            <li>法规依据为公开要求转述，不是法规全文，展开后仍须回原文核对。</li>
            <li>本台只出调查草稿，不是监管结论，也不产生报送报文。</li>
          </ul>
        </section>
      </div>
    </Drawer>
  );
}
