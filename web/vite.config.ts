import { rmSync } from "node:fs";
import { join } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { configDefaults, defineConfig } from "vitest/config";
import { cspOf, readHosting } from "./src/hosting/csp";

/** `public/mockServiceWorker.js` is for `dev:mock` only; every build except `--mode mock` drops it from `dist/`. */
function dropMockWorker(mode: string): Plugin {
  return {
    name: "drop-mock-service-worker",
    apply: "build",
    closeBundle() {
      if (mode === "mock") return;
      rmSync(join(this.environment.config.build.outDir, "mockServiceWorker.js"), { force: true });
    },
  };
}

/** The prod hosting entry's CSP (firebase.json target `app`), serialized as served. The Playwright CSP project previews the build under exactly this header. */
function prodCspHeader(): string {
  const entry = readHosting().find((h) => h.target === "app");
  if (!entry) throw new Error("firebase.json has no `app` hosting entry");
  return Object.entries(cspOf(entry))
    .map(([name, sources]) => [name, ...sources].join(" "))
    .join("; ");
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), dropMockWorker(mode)],
  // Build id for `X-Client-Version`: an explicit VITE_BUILD_SHA wins, else CI's GITHUB_SHA
  // (so no workflow needs an env edit), else `dev`.
  define: {
    "import.meta.env.VITE_BUILD_SHA": JSON.stringify(
      (process.env.VITE_BUILD_SHA || process.env.GITHUB_SHA || "dev").slice(0, 12),
    ),
  },
  // `vite preview` only: the dev server has no CSP, so the e2e `csp` project builds and previews with the prod header.
  preview: { headers: { "Content-Security-Policy": prodCspHeader() } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts", ...(process.env.NIGHTLY_PROPERTIES ? ["./nightly/fast-check.ts"] : [])],
    globals: false,
    // Quarantined files can be run locally with `npm run test:flaky` (FLAKY=1).
    // `e2e_review/**` holds Playwright specs (run via `npm run e2e`), never vitest.
    ...(process.env.NIGHTLY_MUTATION
      ? { include: ["src/auth/next.test.ts", "src/__fuzz_review__/auth.property.test.ts"] }
      : process.env.FLAKY
      ? { include: ["src/**/*.flaky.test.{ts,tsx}"] }
      : { exclude: [...configDefaults.exclude, "e2e_review/**", "**/*.flaky.test.{ts,tsx}"] }),
  },
}));
