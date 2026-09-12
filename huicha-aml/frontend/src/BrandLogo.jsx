/** 顶栏科技印章：扫描取证，不替代产品名。 */
export default function BrandLogo() {
  return (
    <svg className="brand-logo" viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id="xz-plate" x1="8" y1="4" x2="34" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#1b4e86" />
          <stop offset="55%" stopColor="#0d2748" />
          <stop offset="100%" stopColor="#071525" />
        </linearGradient>
        <linearGradient id="xz-scan" x1="6" y1="8" x2="34" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#8ce7ff" />
          <stop offset="100%" stopColor="#2aa4e8" />
        </linearGradient>
        <radialGradient id="xz-core" cx="20" cy="19" r="7" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ff5b55" />
          <stop offset="70%" stopColor="#c8161d" />
          <stop offset="100%" stopColor="#8d0f16" />
        </radialGradient>
        <filter id="xz-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="0.7" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <polygon
        className="brand-logo-plate"
        points="20,2.4 34.6,10.4 34.6,26.6 20,34.6 5.4,26.6 5.4,10.4"
        fill="url(#xz-plate)"
        stroke="#6eb8ea"
        strokeWidth="0.9"
      />
      <polygon
        points="20,6.2 31.2,12.4 31.2,24.8 20,31 8.8,24.8 8.8,12.4"
        fill="none"
        stroke="rgba(140, 231, 255, 0.28)"
        strokeWidth="0.6"
      />

      <g className="brand-logo-reticle" stroke="#e23b3b" strokeWidth="1.15" fill="none" strokeLinecap="square">
        <path d="M8.2 12.2 V8.6 H11.8" />
        <path d="M28.2 8.6 H31.8 V12.2" />
        <path d="M31.8 27.8 V31.4 H28.2" />
        <path d="M11.8 31.4 H8.2 V27.8" />
      </g>

      <g filter="url(#xz-glow)" fill="none" stroke="url(#xz-scan)" strokeWidth="1.15" strokeLinecap="round">
        <path className="brand-logo-arc" d="M12.4 13.2 a9.2 9.2 0 0 1 15.2 0" />
        <path d="M11.6 26.6 a9.6 9.6 0 0 1 4.2-16.4" strokeOpacity="0.45" />
      </g>

      <g className="brand-logo-graph" stroke="#8ce7ff" strokeWidth="0.85" fill="#8ce7ff">
        <line x1="20" y1="11.2" x2="20" y2="14.6" />
        <line x1="12.6" y1="23.6" x2="15.8" y2="21.2" />
        <line x1="27.4" y1="23.6" x2="24.2" y2="21.2" />
        <circle cx="20" cy="10.6" r="1.15" />
        <circle cx="12.2" cy="24.2" r="1.05" />
        <circle cx="27.8" cy="24.2" r="1.05" />
      </g>

      <polygon points="20,14.2 25.4,19.4 20,24.6 14.6,19.4" fill="url(#xz-core)" />
      <polygon points="20,16.1 23.4,19.4 20,22.7 16.6,19.4" fill="#fff6f4" fillOpacity="0.92" />
      <rect x="19.35" y="16.6" width="1.3" height="8.8" rx="0.4" fill="#c8161d" />
    </svg>
  );
}
