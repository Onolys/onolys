import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// index.html loads /theme-init.js: the one pre-paint theme script, taken from @onolys/common (git-ignored copy in public/).
const publicDir = fileURLToPath(new URL("./public", import.meta.url));
mkdirSync(publicDir, { recursive: true });
copyFileSync(createRequire(import.meta.url).resolve("@onolys/common/theme-init.js"), `${publicDir}/theme-init.js`);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // One copy of each shared library, including the one @onolys/common itself imports.
    dedupe: ["react", "react-dom", "react-router", "firebase", "@tanstack/react-query", "@onolys/common", "openapi-fetch", "lucide-react"],
  },
  test: { environment: "node", setupFiles: ["./src/testSetup.ts"] },
});
