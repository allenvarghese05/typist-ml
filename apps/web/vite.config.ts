/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server for one machine (D06). A fixed host and port keep the dev origin stable, and
// strictPort makes Vite fail instead of silently moving to another port. The API (T0.3) listens
// on 127.0.0.1:8000; /api requests are proxied there, so the browser needs no CORS.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    // Unit tests live next to the code in src/; e2e/ is reserved for Playwright.
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "node",
  },
});
