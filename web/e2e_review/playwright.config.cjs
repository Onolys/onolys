// Run (mock mode, default): see README.md. Live-ish mode: E2E_MODE=live runs only tests tagged @live.
const { defineConfig } = require("@playwright/test");
const path = require("path");

const PORT = process.env.E2E_PORT || "5173";
const LIVE = process.env.E2E_MODE === "live";
// Live mode needs Firestore emulator (:8081) + api (:8000, AUTH_MODE=fake, ADAPTERS=stub) already running, see
// docs/agent_files/review-full-app-20261121/RUN.md
const LIVE_ENV = { VITE_USE_MOCKS: "false", VITE_AUTH_MODE: "fake", VITE_API_BASE_URL: "http://127.0.0.1:8000/v1", VITE_FIRESTORE_EMULATOR: "127.0.0.1:8081", VITE_FIREBASE_PROJECT_ID: "demo-onolys", VITE_FIREBASE_DATABASE: "(default)", VITE_FIRESTORE_DATABASE: "(default)" };

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.cjs",
  outputDir: path.join(__dirname, "test-results"), // vite ignores **/test-results/**; other writes under web/ trigger a full reload
  fullyParallel: true, // every test is independent (own context, in-memory fake auth + MSW state): safe for --shard=i/n
  workers: process.env.CI ? 2 : 4,
  timeout: 90_000,
  expect: { timeout: 8_000 },
  grep: LIVE ? /@live/ : undefined,
  grepInvert: LIVE ? undefined : /@live/, // default (CI) = mock only
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`, // must be `localhost`, not 127.0.0.1 (api CORS)
    deviceScaleFactor: 1,
    viewport: { width: 1280, height: 720 },
    trace: "off",
  },
  webServer: {
    command: `npm run ${LIVE ? "dev:live" : "dev:mock"} -- --port ${PORT} --strictPort`,
    cwd: path.join(__dirname, ".."),
    env: LIVE ? { ...process.env, ...LIVE_ENV } : undefined,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
