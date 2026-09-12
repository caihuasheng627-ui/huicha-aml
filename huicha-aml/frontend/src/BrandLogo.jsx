/** 内网台标：静默方印，不做扫描光效。 */
export default function BrandLogo() {
  return (
    <svg className="brand-logo" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" fill="#3a5a7c" />
      <text
        x="14"
        y="19.5"
        textAnchor="middle"
        fill="#fff"
        fontSize="13"
        fontFamily='"Noto Sans SC", "PingFang SC", sans-serif'
        fontWeight="600"
      >
        查
      </text>
    </svg>
  );
}
