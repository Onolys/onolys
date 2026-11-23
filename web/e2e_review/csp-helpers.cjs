// Shared by csp.spec.cjs and visual.spec.cjs (the `csp` project: built mock app under the exact prod CSP, see playwright.config.cjs).
const path = require("path");
const fs = require("fs");
const AxeBuilder = require("@axe-core/playwright").default;
const { expect } = require("@playwright/test");

const SHOTS = path.join(__dirname, "test-results", "shots"); // gitignored; uploaded by the CI web-e2e job

/** Record every CSP violation: the DOM `securitypolicyviolation` event (survives navigations via an init script) and CSP console errors. */
async function watchCsp(page) {
  const violations = [];
  page.on("console", (m) => {
    if (/content security policy|refused to (load|apply|execute|connect|create)/i.test(m.text())) violations.push(`console: ${m.text().slice(0, 300)}`);
  });
  page.on("pageerror", (e) => violations.push(`pageerror: ${String(e).slice(0, 300)}`));
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      window.__csp.push(`${e.violatedDirective} blocked ${e.blockedURI || "inline"} (${e.sourceFile || ""}:${e.lineNumber || 0})`);
    });
  });
  return {
    async all() {
      const fromDom = await page.evaluate(() => window.__csp || []).catch(() => []);
      return [...violations, ...fromDom.map((v) => `dom: ${v}`)];
    },
  };
}

/** Prove the listener is armed: the page has a CSP header (so inline style would be blocked). */
async function expectStrictPolicy(page) {
  const res = await page.request.get(page.url());
  expect(res.headers()["content-security-policy"]).toMatch(/style-src 'self'(;|$)/);
}

/** axe color-contrast + critical violations in the current scheme; returns violation summaries. */
async function axeGate(page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations
    .filter((v) => v.id === "color-contrast" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes.slice(0, 4).map((n) => n.target.join(" ") + " :: " + (n.any[0] && n.any[0].message || "")).join(" | ")}`);
}

async function shotTo(page, name) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

module.exports = { SHOTS, watchCsp, expectStrictPolicy, axeGate, shotTo };
