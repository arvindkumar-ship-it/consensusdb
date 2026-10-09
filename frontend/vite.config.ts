import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev me /api -> router (127.0.0.1:8000). Router ka port badla ho to ROUTER_URL set karo.
const target = process.env.ROUTER_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
});
