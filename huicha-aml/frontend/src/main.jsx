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
        colorPrimary: "#3a5a7c",
        colorLink: "#3a5a7c",
        colorError: "#b42318",
        colorSuccess: "#2d6a4f",
        colorWarning: "#8a6914",
        borderRadius: 2,
        fontFamily:
          '"IBM Plex Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: 13,
        colorText: "#2c3138",
        colorTextSecondary: "#66707c",
        colorBorder: "#d5d9e0",
        colorBgLayout: "#eceef1",
        colorBgContainer: "#ffffff",
      },
      components: {
        Button: { controlHeight: 32, fontWeight: 500 },
        Table: { headerBg: "#f3f4f6", headerColor: "#2c3138" },
        Tag: { borderRadiusSM: 2 },
      },
    }}
  >
    <App />
  </ConfigProvider>
);
