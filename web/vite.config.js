import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  // The moment this build was made; the app shows it as its version.
  define: { __BUILT__: JSON.stringify(new Date().toISOString()) },
  // React and Recharts make one ~560 kB bundle (~170 kB gzipped); fine for one private app.
  build: { outDir: "dist", chunkSizeWarningLimit: 700 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.js"],
  },
});
