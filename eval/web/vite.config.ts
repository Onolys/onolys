import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/** The prod app's auth code (one copy, shared by alias; see tsconfig `paths`). */
const prodAuth = fileURLToPath(new URL("../../web/src/auth", import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@prod-auth": prodAuth },
    // Prod sources live outside this package: force their bare imports to resolve from eval/web/node_modules (one copy).
    dedupe: ["react", "react-dom", "react-router", "firebase", "@tanstack/react-query", "@onolys/ui", "openapi-fetch"],
  },
  server: { fs: { allow: [fileURLToPath(new URL("../..", import.meta.url))] } },
  test: { environment: "node" },
});
