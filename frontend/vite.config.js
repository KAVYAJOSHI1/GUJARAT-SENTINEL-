import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server runs on :3000 per DEVELOPER_README (Isha) §10.
// /api and /ws are proxied to Vanshal's FastAPI backend so the same
// relative paths work in dev and in the production `dist` bundle.
const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";
const wsTarget = proxyTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT) || 3000,
    host: true,
    proxy: {
      "/api": { target: proxyTarget, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
