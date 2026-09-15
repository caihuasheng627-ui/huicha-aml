import { Drawer, Tag } from "antd";
import BrandLogo from "./BrandLogo.jsx";
import { ApproachComparison } from "./CasePanels.jsx";

const STEPS = [
  ["选告警", "左栏「我的待办」按待办 / 已办切换，也可按客户名、告警类型或案件号搜索。"],
  ["生成草稿", "中栏点「开始调查」。系统取证并写出调查底稿，全过程可回溯。"],
  ["读建议与证据", "对照规则建议与 AI 建议，点编号回到流水、客户资料与制度摘录。"],
  ["提交复核", "调查员登录后填写意见，点「提交复核」。事实回查未通过时须写说明。"],
  ["复核签发", "合规岗登录后「同意签发」或「退回调查」。系统不会自动报送。"],
];

const PANELS = [
  ["左栏", "待办告警队列、筛选与反馈闭环统计。"],
  ["中栏", "案件舞台：指标卡、三方对照、进模脱敏凭证、慧查agent 面板、风险因子、时间线、反事实、法规依据、调查过程、报告草稿与待补证清单。底部是签发与导出。"],
  ["右栏", "证据与关联：客户 KYC 卡、资金图谱、证据分组、制度与类型学、交易流水和操作审计。"],
];

const CONCLUSIONS = [
  ["排除", "ok", "证据足以说明交易与客户身份、职业或经营特征相符，但仍须写明排除理由。"],
  ["继续观察", "warn", "疑点未排除也未达上报门槛，保留监测。"],
  ["建议上报", "risk", "仅为草稿建议，须调查员签发后再由复核与总部审定流程处理。"],
];

const BLOCKERS = [
  ["事实回查未通过", "报告里出现了本案证据范围之外的账号、金额或编号，签发按钮锁定，须重跑或人工修改。"],
  ["慧查agent 证据契约未通过", "理由缺引用、引用了工具范围外的编号，或建议上报却没有支持证据，整份 AI 建议作废，只保留规则对照。"],
  ["出站检漏失败", "发给模型的上下文仍含未脱敏账号或已登记姓名，本轮调查中止，不会把明文送出。"],
];

const PRIVACY_RULES = [
  ["工作台", "客户姓名、账号、流水对调查员明文展示，便于核对证据。"],
  ["进模替换", "姓名 → CLIENT_00n，账号 → ACCOUNT_00n，客户号 → CUST_00n。渠道名 CASH- / POS- / RELATIVE- 保留语义。"],
  ["交易编号", "TX-* 不替换，否则慧查agent 无法按编号引用，Skeptic 也无法校验。"],
  ["出站检漏", "替换后再扫一遍；命中 6222- 形态或未替换的登记字段即中止，不调用模型。"],
  ["导出", "须先登录。底稿写明脱敏策略和导出人，仍是调查草稿，不是报送报文。"],
];

const SWITCHES = [
  ["慧查agent", "正常模式下默认启用。只影响下一次重跑，不会改写已打开的历史草稿。"],
  ["实验模式", "开启后才能关闭慧查agent 做消融对照，用于验证「有无慧查agent」的差异。"],
  ["幻觉演示", "实验模式专用，故意注入不实表述，用来演示事实回查与签发拦截确实生效。"],
];

const KEYS = [
  ["0", "进入比赛演示，锁定案例 L 主线（生成草稿后按条带三步走）。"],
  ["1 / 2 / 3 / 4 / 5 / 6", "打开案例 A 排除、B 拆分、C 归集、F 观察、L 多层、H 抽数（只打开历史草稿，不重跑）。"],
  ["点击编号", "报告、理由、法规、图谱里的编号都可点，用于回溯原始证据。"],
];

export default function SystemManual({ open, onClose, health }) {
  const privacyPolicy = health?.privacy?.policy || "privacy_v2";
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
              <em>人负责最终决策</em>。调查员提交复核，合规岗签发。系统不连接真实银行，不会自动报送。实验室入口在右上角。
            </p>
          </div>
        </div>

        <section className="manual-sec">
          <h4>一、和普通 AI 有什么不同</h4>
          <p className="manual-note" style={{ marginTop: 0 }}>
            同样可以接大模型，但循证慧查把「慧查agent」关在证据、护栏、脱敏出站和人工签发之内——对照表如下，工作台只展示本案调查结果。
          </p>
          <ApproachComparison />
        </section>

        <section className="manual-sec">
          <h4>二、五步走完一个案子</h4>
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
          <h4>三、三栏分别看什么</h4>
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
          <h4>四、结论三档</h4>
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
          <h4>五、什么情况下不能签发</h4>
          <ul className="manual-list">
            {BLOCKERS.map(([name, desc]) => (
              <li key={name}>
                <b className="risk">{name}</b>
                <span>{desc}</span>
              </li>
            ))}
          </ul>
          <p className="manual-note">签发与导出须先登录，签发人/导出人会写入审计留痕；AI 不得自动报送监测中心。</p>
        </section>

        <section className="manual-sec">
          <h4>六、隐私与出站</h4>
          <p className="manual-note" style={{ marginTop: 0 }}>
            策略 {privacyPolicy}：明文只给调查员看，占位符才给模型看。这是竞赛原型脱敏，不是银行级加密或数据不出域。
          </p>
          <dl className="manual-dl">
            {PRIVACY_RULES.map(([name, desc]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{desc}</dd>
              </div>
            ))}
          </dl>
          <p className="manual-note">
            调查完成后，中栏会出现「进模脱敏」标签（登记了多少姓名/账号、出站几次已检漏）。调查过程里也有 Privacy 步骤。金额、行业、交易模式仍会进模型，因为研判需要这些字段。
          </p>
        </section>

        <section className="manual-sec">
          <h4>七、顶栏策略开关</h4>
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
          <h4>八、快捷操作</h4>
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
          <h4>九、比赛演示（3 分钟主线）</h4>
          <p className="manual-note" style={{ marginTop: 0 }}>
            顶栏「比赛演示」或快捷键 0，锁定案例 L。只带评委看三件事：点证据编号、护栏后不是已报送、登录签发进审计。
            A/B/C/F/H、幻觉拦截、关闭慧查agent 都是备用枝。合成对照不是生产准确率，人效数字未测完不报提升百分比。
          </p>
        </section>

        <section className="manual-sec">
          <h4>十、评委常问（第一句）</h4>
          <dl className="manual-dl">
            <div>
              <dt>准确率多少</dt>
              <dd>合成对照不是生产准确率，现场看引用和拦截。</dd>
            </div>
            <div>
              <dt>数据是真的吗</dt>
              <dd>全部合成，不接核心。试点才只读接告警队列。</dd>
            </div>
            <div>
              <dt>去掉大模型</dt>
              <dd>能降级，但没有证据综合建议和可用全文草稿。</dd>
            </div>
            <div>
              <dt>责任谁负</dt>
              <dd>调查员签发；系统不会变成已报送。</dd>
            </div>
            <div>
              <dt>和监测什么关系</dt>
              <dd>他们做疑不疑，我们做为什么、证据在哪、报告怎么写。</dd>
            </div>
          </dl>
          <p className="manual-note">完整 20 题与禁语见仓库根目录《答辩作战手册》。</p>
        </section>

        <section className="manual-sec">
          <h4>十一、运行环境</h4>
          <div className="manual-chips">
            <Tag>版本 {health?.version || "—"}</Tag>
            <Tag color={health?.llm && health.llm !== "off" ? "blue" : "red"}>
              模型 {health?.model || health?.llm || "未配置"}
            </Tag>
            <Tag>知识库 {health?.kb_docs ?? "—"} 条</Tag>
            <Tag>检索 {health?.kb_retrieval || "hybrid-keyword-tfidf"}</Tag>
            <Tag color="orange">数据 {health?.data_note || "synthetic"}</Tag>
            <Tag color="geekblue">出站 {privacyPolicy}</Tag>
          </div>
          <p className="manual-note">{health?.stack || "FastAPI + SQLite + React（竞赛原型）"}</p>
        </section>

        <section className="manual-sec">
          <h4>十二、诚实边界</h4>
          <ul className="manual-limits">
            {(health?.limitations || []).map((x) => (
              <li key={x}>{x}</li>
            ))}
            <li>法规依据含现行法律规章官方条款（按条切块混合检索）与作业转述；签发前仍须回原文核对。</li>
            <li>本台只出调查草稿，不是监管结论，也不产生报送报文。</li>
            <li>SQLite 调查载荷仍明文存储；脱敏只发生在调用大模型之前。</li>
          </ul>
        </section>
      </div>
    </Drawer>
  );
}
