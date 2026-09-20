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
        colorPrimary: "#012870",
        colorLink: "#012870",
        colorError: "#8F1D27",
        colorSuccess: "#3D5A45",
        colorWarning: "#8A6A2F",
        borderRadius: 0,
        fontFamily:
          '"Source Sans 3", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: 13,
        colorText: "#1A2330",
        colorTextSecondary: "#5C6B7A",
        colorBorder: "#C5CDD8",
        colorBgLayout: "#E8EEF5",
        colorBgContainer: "#F6F8FB",
      },
      components: {
        Button: { controlHeight: 30, fontWeight: 500, borderRadius: 0 },
        Table: { headerBg: "#012870", headerColor: "#F6F8FB", headerSplitColor: "#163E7A", borderRadius: 0 },
        Tag: { borderRadiusSM: 0 },
        Switch: { colorPrimary: "#3D5A45" },
        Modal: { borderRadiusLG: 0 },
        Drawer: { colorBgElevated: "#F6F8FB" },
        Input: { borderRadius: 0, controlHeight: 30 },
        Message: { borderRadiusLG: 0 },
        Alert: { borderRadiusLG: 0 },
        Divider: { colorSplit: "#C5CDD8" },
        Timeline: { dotBg: "#012870" },
      },
    }}
  >
    <App />
  </ConfigProvider>
);
