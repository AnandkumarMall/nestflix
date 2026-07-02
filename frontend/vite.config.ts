import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During dev, proxy /api to the FastAPI backend so the frontend can use relative URLs.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Output into frontend/dist; FastAPI serves this in production.
    outDir: "dist",
  },
});
