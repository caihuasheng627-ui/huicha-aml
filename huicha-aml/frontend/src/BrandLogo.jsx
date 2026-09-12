import logoPng from "./assets/logo.png";

/**
 * 循证慧查专属台标：
 * 采用用户指定的科技风 AML 盾牌 + 穿透节点 + 探查放大镜 Logo。
 * 透明 PNG 矢量级高清渲染，支持多尺寸传参。
 */
export default function BrandLogo({ size = 34, className = "" }) {
  const classes = ["brand-logo", className].filter(Boolean).join(" ");
  return (
    <img
      src={logoPng}
      alt="循证慧查 Logo"
      className={classes}
      width={size}
      height={size}
      style={{
        width: size,
        height: size,
        objectFit: "contain",
      }}
      draggable={false}
    />
  );
}
