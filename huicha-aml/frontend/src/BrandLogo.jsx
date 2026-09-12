/** 顶栏科技印章：扫描取证，按 40px 可读性画，不替代产品名。 */
export default function BrandLogo() {
  return (
    <svg className="brand-logo" viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id="xz-plate" x1="6" y1="2" x2="34" y2="38" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#2a6aad" />
          <stop offset="50%" stopColor="#0f3060" />
          <stop offset="100%" stopColor="#081526" />
        </linearGradient>
        <radialGradient id="xz-core" cx="20" cy="20" r="8" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ff7a72" />
          <stop offset="55%" stopColor="#e31b22" />
          <stop offset="100%" stopColor="#8c1015" />
        </radialGradient>
      </defs>

      <polygon
        points="20,1.6 36,10.6 36,27.6 20,36.6 4,27.6 4,10.6"
        fill="url(#xz-plate)"
        stroke="#8ee0ff"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />

      <g stroke="#ff4d4f" strokeWidth="1.8" fill="none" strokeLinecap="square">
        <path d="M6.2 12.2 V6.6 H11.8" />
        <path d="M28.2 6.6 H33.8 V12.2" />
        <path d="M33.8 27.8 V33.4 H28.2" />
        <path d="M11.8 33.4 H6.2 V27.8" />
      </g>

      <path
        className="brand-logo-arc"
        d="M11 14.2 a11.2 11.2 0 0 1 18 0"
        fill="none"
        stroke="#9aefff"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <line x1="7.6" y1="20.2" x2="13.2" y2="20.2" stroke="#9aefff" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="26.8" y1="20.2" x2="32.4" y2="20.2" stroke="#9aefff" strokeWidth="1.5" strokeLinecap="round" />

      <polygon points="20,12.2 28.2,20.2 20,28.2 11.8,20.2" fill="url(#xz-core)" />
      <polygon points="20,15.4 24.6,20.2 20,25 15.4,20.2" fill="#fff4f1" fillOpacity="0.88" />
    </svg>
  );
}
