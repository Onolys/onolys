const path = require("path");
const fs = require("fs");
const { expect } = require("@playwright/test");

const SHOTS = path.resolve(__dirname, "../../docs/agent_files/review-full-app-20261121/e2e-shots");
const FIX = (f) => path.join(__dirname, "fixtures", f);
const PW = "password1";

async function shot(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `spec-${name}.png`) });
}

/** Collect console errors, page errors, failed requests and 4xx/5xx responses (noise filtered). */
function collect(page) {
  const out = { console: [], pageerrors: [], failed: [], http: [], requests: [] };
  page.on("console", (m) => {
    if (m.type() === "error") out.console.push(m.text().slice(0, 300));
  });
  page.on("pageerror", (e) => out.pageerrors.push(String(e).slice(0, 300)));
  page.on("requestfailed", (r) => {
    if (/^blob:|ERR_ABORTED/.test(r.url() + (r.failure()?.errorText || ""))) return; // media probe / vite aborts
    out.failed.push(`${r.method()} ${r.url().slice(0, 150)}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400) out.http.push(`${r.status()} ${r.request().method()} ${r.url().slice(0, 150)}`);
  });
  page.on("request", (r) => out.requests.push(`${r.method()} ${r.url()}`));
  return out;
}

const field = (page, label) => page.getByLabel(label, { exact: true });
async function signUp(page, email, pw = PW) {
  await page.goto("/signup");
  await field(page, "Email").fill(email);
  await field(page, "Password").fill(pw);
  await page.getByRole("button", { name: "Create account" }).click();
}
async function signUpVerified(page, email = "user@example.com") {
  await signUp(page, email);
  await page.getByRole("button", { name: "I've verified" }).click();
  await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible();
}
/** In-app navigation without reload (fake auth state lives in memory and a reload would sign the user out). */
async function spa(page, url) {
  await page.evaluate((u) => {
    history.pushState({}, "", u);
    dispatchEvent(new PopStateEvent("popstate"));
  }, url);
}
async function signOutViaSettings(page) {
  await page.locator("header nav a", { hasText: "Settings" }).click();
  await page.locator("main").getByRole("button", { name: "Sign out" }).click();
}
const navLinks = (page) => page.locator("header nav a").allTextContents();
const hasHScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
const path_ = (page) => { const u = new URL(page.url()); return u.pathname + u.search; };

const LIVE = process.env.E2E_MODE === "live";
module.exports = { LIVE, SHOTS, FIX, PW, shot, collect, field, signUp, signUpVerified, spa, signOutViaSettings, navLinks, hasHScroll, path_ };
