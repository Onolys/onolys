const path = require("path");
const fs = require("fs");
const { expect } = require("@playwright/test");

const SHOTS = path.join(__dirname, "test-results", "shots"); // gitignored; only written with E2E_SHOTS=1
const FIX = (f) => path.join(__dirname, "fixtures", f);
const PW = "password1";

async function shot(page, name) {
  if (process.env.E2E_SHOTS !== "1") return;
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

// Sign-in runs on the Firebase Auth emulator (`.env.mock`; `npm run e2e` expects it on 127.0.0.1:9099, see README).
// Every spec signs up its own fresh user: the address is made unique per page so tests never share an account.
const EMULATOR = process.env.E2E_AUTH_EMULATOR_URL || "http://127.0.0.1:9099";
const PROJECT = "demo-onolys";
const KEY = "fake-api-key";
const emails = new WeakMap();
/** The unique address this page signs up with for the readable address `email` (`a@x.com` -> `a-k3j9x2@x.com`). */
function emailFor(page, email) {
  const known = emails.get(page) ?? new Map();
  emails.set(page, known);
  if (!known.has(email)) {
    const [local, domain] = email.split("@");
    const tag = Math.random().toString(36).slice(2, 8);
    known.set(email, local.length + tag.length + domain.length + 2 > 254 ? email : `${local}-${tag}@${domain}`);
  }
  return known.get(email);
}
const emulator = (path, body, headers = {}) =>
  fetch(`${EMULATOR}/identitytoolkit.googleapis.com/v1/${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  }).then((r) => r.json());
/** Follows the verification link out of band: the account is verified on the server, the app learns it on "I've verified". */
async function verifyEmail(page, email, pw = PW) {
  const { localId } = await emulator(`accounts:signInWithPassword?key=${KEY}`, { email: emailFor(page, email), password: pw, returnSecureToken: true });
  await emulator(`projects/${PROJECT}/accounts:update`, { localId, emailVerified: true }, { authorization: "Bearer owner" });
}

/** Presses "I've verified" if the verify page is still showing it (it may already have noticed the verification and moved on). */
const confirmVerified = (page) => page.getByRole("button", { name: "I've verified" }).click({ timeout: 3_000 }).catch(() => {});

const field = (page, label) => page.getByLabel(label, { exact: true });
async function signUp(page, email, pw = PW) {
  await page.goto("/signup");
  await field(page, "Email").fill(emailFor(page, email));
  await field(page, "Password").fill(pw);
  await field(page, "Confirm password").fill(pw);
  await page.getByRole("button", { name: "Create account" }).click();
}
async function signUpVerified(page, email = "user@example.com") {
  await signUp(page, email);
  await expect(page).toHaveURL(/verify-email/);
  await verifyEmail(page, email);
  await confirmVerified(page);
  await expect(page.getByRole("heading", { name: /^Welcome/ })).toBeVisible();
}
/** In-app navigation without reload (a full reload would restart the app; the signed-in user survives it, but the mock backend's state does not). */
async function spa(page, url) {
  await page.evaluate((u) => {
    history.pushState({}, "", u);
    dispatchEvent(new PopStateEvent("popstate"));
  }, url);
}
/** Open the avatar account menu and choose an item (Settings link / Sign out button). */
async function accountMenu(page, item) {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: item, exact: true }).click();
  await expect(page.getByRole("menu")).toHaveCount(0); // Radix exit animation: reopening the trigger mid-close re-dismisses it
}
async function signOutViaSettings(page) {
  await accountMenu(page, "Settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeFocused(); // menu close must not steal page-change focus
  await accountMenu(page, "Sign out");
}
/** From the New Session chooser (nav "New Session"), open the upload page via the "Rate a recording" card. */
async function openUpload(page) {
  await page.locator("header nav a", { hasText: "New Session" }).click();
  await page.getByRole("main").getByRole("link", { name: "New session", exact: true }).click();
}
const navLinks = (page) => page.locator("header nav a").allTextContents();
const hasHScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
const path_ = (page) => { const u = new URL(page.url()); return u.pathname + u.search; };

module.exports = { SHOTS, FIX, PW, shot, collect, field, emailFor, verifyEmail, confirmVerified, signUp, signUpVerified, spa, openUpload, accountMenu, signOutViaSettings, navLinks, hasHScroll, path_ };
