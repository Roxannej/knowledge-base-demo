/**
 * Vite 配置：React 插件 + 开发代理（/api -> 后端），避免本地跨域。
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
        // 上传大文件 + 本地 embedding 可能较慢，避免代理默认超时中断
        timeout: 300_000,
        proxyTimeout: 300_000,
      },
    },
  },
});
