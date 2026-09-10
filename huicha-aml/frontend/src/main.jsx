import React from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <ConfigProvider
    locale={zhCN}
    theme={{
      token: {
        colorPrimary: "#1b4f8a",
        colorLink: "#1b4f8a",
        colorError: "#c8161d",
        colorSuccess: "#0f7b4a",
        colorWarning: "#b45309",
        borderRadius: 6,
        fontFamily:
          '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", "Source Han Sans SC", sans-serif',
        fontSize: 13,
        colorText: "#1e293b",
        colorTextSecondary: "#64748b",
        colorBorder: "#e2e8f0",
        colorBgLayout: "#eef1f6",
      },
      components: {
        Button: { controlHeight: 32 },
        Table: { headerBg: "#f4f7fb", headerColor: "#334155" },
        Tag: { borderRadiusSM: 4 },
      },
    }}
  >
    <App />
  </ConfigProvider>
);
