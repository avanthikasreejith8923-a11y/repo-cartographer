import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/auth": {
        target: process.env.VITE_BACKEND_PROXY_URL || "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/health": {
        target: process.env.VITE_BACKEND_PROXY_URL || "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
