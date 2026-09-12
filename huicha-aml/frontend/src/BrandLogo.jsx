/**
 * 循证慧查专属台标：
 * 融合「循证天平/盾牌」+「网格穿透节点」+「慧查折线光标」概念，
 * 采用深海渊蓝 (#0f2744) 渐变与经纬金 (#d4af37) 细线点缀，庄重权威且具金融科技质感。
 */
export default function BrandLogo({ size = 32 }) {
  return (
    <svg
      className="brand-logo"
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden="true"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="hc-badge-bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1e3a5f" />
          <stop offset="50%" stopColor="#0f2744" />
          <stop offset="100%" stopColor="#0a192c" />
        </linearGradient>
        <linearGradient id="hc-gold" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f3d37a" />
          <stop offset="100%" stopColor="#c59b27" />
        </linearGradient>
        <linearGradient id="hc-cyan" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6ee7b7" />
          <stop offset="100%" stopColor="#38bdf8" />
        </linearGradient>
        <filter id="hc-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.2" floodColor="#000" floodOpacity="0.35" />
        </filter>
      </defs>

      {/* 外框：八角几何盾印，寓意合规与风控护栏 */}
      <rect
        x="1.5"
        y="1.5"
        width="29"
        height="29"
        rx="6"
        fill="url(#hc-badge-bg)"
        stroke="#2d4a6f"
        strokeWidth="1"
        filter="url(#hc-glow)"
      />

      {/* 细密经纬网格暗纹 */}
      <path
        d="M6 16h20M16 6v20"
        stroke="#ffffff"
        strokeOpacity="0.08"
        strokeWidth="1"
        strokeDasharray="2 2"
      />

      {/* 天平 / 循证双向穿透结构（外层护栏） */}
      <path
        d="M16 6.5L25 11v6.2c0 5.2-3.8 8.8-9 10.3-5.2-1.5-9-5.1-9-10.3V11l9-4.5z"
        fill="none"
        stroke="url(#hc-gold)"
        strokeWidth="1.2"
        strokeLinejoin="round"
        strokeOpacity="0.85"
      />

      {/* 核心「查」字篆意骨架与经纬穿透节点：象征证据锚点与图谱关联 */}
      <path
        d="M11.5 13h9M16 9.5v8.5M12.5 18h7M13.5 21.5l2.5-3.5 2.5 3.5"
        stroke="#ffffff"
        strokeWidth="1.35"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* 智能判定锚点：青碧高亮脉冲点 */}
      <circle cx="16" cy="9.5" r="1.3" fill="url(#hc-cyan)" />
      <circle cx="11.5" cy="13" r="1.1" fill="url(#hc-gold)" />
      <circle cx="20.5" cy="13" r="1.1" fill="url(#hc-gold)" />
    </svg>
  );
}

