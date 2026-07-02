import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: Number(process.env.JAVSTORY_VITE_PORT || 5173),
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      "/health": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        timeout: 5000,
        proxyTimeout: 5000,
      },
    },
  },
});
