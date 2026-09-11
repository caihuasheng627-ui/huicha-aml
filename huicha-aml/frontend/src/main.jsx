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
        colorPrimary: "#1d4f86",
        colorLink: "#1d4f86",
        colorError: "#c8161d",
        colorSuccess: "#1a7a4c",
        colorWarning: "#c47a12",
        borderRadius: 4,
        fontFamily:
          '"IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: 13,
        colorText: "#1c2838",
        colorTextSecondary: "#5b6b80",
        colorBorder: "#d5dde8",
        colorBgLayout: "#e8edf3",
        colorBgContainer: "#fbfcfe",
      },
      components: {
        Button: { controlHeight: 32, fontWeight: 600 },
        Table: { headerBg: "#eef3f8", headerColor: "#1c2838" },
        Tag: { borderRadiusSM: 2 },
      },
    }}
  >
    <App />
  </ConfigProvider>
);
