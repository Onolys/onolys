// Run (mock mode): see README.md.
const { defineConfig } = require("@playwright/test");
const path = require("path");

const PORT = process.env.E2E_PORT || "5173";

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "*.spec.cjs",
  outputDir: path.join(__dirname, "test-results"), // vite ignores **/test-results/**; other writes under web/ trigger a full reload
  fullyParallel: true, // every test is independent (own context, in-memory fake auth + MSW state): safe for --shard=i/n
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : 4,
  timeout: 90_000,
  expect: { timeout: 8_000 },
  reporter: process.env.CI ? "github" : [["list"]],
  grepInvert: process.env.CI ? /@live/ : undefined, // no @live specs remain; guards against re-adding emulator-only tests to CI
  use: {
    baseURL: `http://localhost:${PORT}`, // must be `localhost`, not 127.0.0.1 (api CORS)
    deviceScaleFactor: 1,
    viewport: { width: 1280, height: 720 },
    trace: "off",
  },
  webServer: {
    command: `npm run dev:mock -- --port ${PORT} --strictPort`,
    cwd: path.join(__dirname, ".."),
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
