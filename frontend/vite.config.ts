import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BACKEND = "http://localhost:8000";

const proxy = {
  "/api": { target: BACKEND, changeOrigin: false },
  "/tiles": { target: BACKEND, changeOrigin: false },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
  build: {
    target: "es2022",
    sourcemap: true,
    // MapLibre is about a megabyte on its own and changes far less often than
    // the app, so it gets its own long-lived chunk.
    chunkSizeWarningLimit: 1100,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "maplibre", test: /node_modules[\\/](maplibre-gl|@maplibre)[\\/]/ },
            { name: "react", test: /node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/ },
          ],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    css: true,
    restoreMocks: true,
  },
});
