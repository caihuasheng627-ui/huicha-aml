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
        colorPrimary: "#0A1E33",
        colorLink: "#1A4A73",
        colorError: "#8E1E2A",
        colorSuccess: "#1A6B63",
        colorWarning: "#8A6914",
        borderRadius: 2,
        fontFamily:
          '"Source Sans 3", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: 13,
        colorText: "#1A2330",
        colorTextSecondary: "#5C6B7A",
        colorBorder: "#B7C0CB",
        colorBgLayout: "#E8EDF2",
        colorBgContainer: "#ffffff",
      },
      components: {
        Button: { controlHeight: 30, fontWeight: 500, borderRadius: 2 },
        Table: { headerBg: "#0A1E33", headerColor: "#F4F7FA", headerSplitColor: "#1A3348" },
        Tag: { borderRadiusSM: 0 },
        Switch: { colorPrimary: "#1A6B63" },
        Modal: { borderRadiusLG: 0 },
        Drawer: { colorBgElevated: "#ffffff" },
        Input: { borderRadius: 2, controlHeight: 30 },
        Message: { borderRadiusLG: 0 },
        Alert: { borderRadiusLG: 0 },
        Divider: { colorSplit: "#B7C0CB" },
      },
    }}
  >
    <App />
  </ConfigProvider>
);
