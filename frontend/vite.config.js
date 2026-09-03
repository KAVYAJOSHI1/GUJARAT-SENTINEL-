import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server runs on :3000 per DEVELOPER_README (Isha) §10.
// /api and /ws are proxied to Vanshal's FastAPI backend so the same
// relative paths work in dev and in the production `dist` bundle.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
