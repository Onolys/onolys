// Visual + a11y evidence (PRD R10, Decision 5): light/dark screenshots (no pixel diff) and an axe gate
// (color-contrast + critical violations) per screen in both schemes. Runs in the `csp` project (built app, prod CSP).
const { test, expect } = require("@playwright/test");
const { FIX, signUp, spa, openUpload, accountMenu } = require("./helpers.cjs");
const { watchCsp, axeGate, shotTo } = require("./csp-helpers.cjs");

/**
 * Screens whose axe gate is waived in a scheme until the task that migrates them (Tasks 3-8 of 02-app-migration).
 * Key `<screen>@<scheme>` -> task. Anything not listed here must be axe-clean. Empty = fully gated.
 */
const TODO = {};

const wait = (page) => page.waitForLoadState("networkidle").catch(() => {});

async function verified(page, email) {
  await signUp(page, email);
  await page.getByRole("button", { name: "I've verified" }).click();
  await expect(page.getByRole("heading", { name: "New Session", exact: true })).toBeVisible();
}

const SIGNED_OUT = {
  login: (p) => p.goto("/login"),
  signup: (p) => p.goto("/signup"),
  "forgot-password": (p) => p.goto("/forgot-password"),
  "auth-action": (p) => p.goto("/auth/action?mode=resetPassword&oobCode=x"),
  sample: (p) => p.goto("/sample"),
  privacy: (p) => p.goto("/privacy"),
  terms: (p) => p.goto("/terms"),
  "not-found": (p) => p.goto("/nope"),
  "sample-transcript-dialog": async (p) => {
    await p.goto("/sample");
    await p.getByRole("button", { name: "Open coded transcript" }).click();
    await expect(p.locator("dialog[open]")).toBeVisible();
  },
};

const SIGNED_IN = {
  verify: async (p) => {
    await signUp(p, "v@example.com");
    await expect(p.getByRole("button", { name: "I've verified" })).toBeVisible();
  },
  chooser: async (p) => { await verified(p, "a@example.com"); },
  "sessions-list": async (p) => { await verified(p, "b@example.com"); await spa(p, "/sessions"); await expect(p.getByRole("heading", { level: 1 })).toBeVisible(); },
  "sessions-list-populated": async (p) => {
    await verified(p, "h@example.com");
    for (const goal of ["One", "Two"]) {
      await openUpload(p);
      await p.getByLabel("Change goal").fill(goal);
      await p.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
      await p.getByRole("button", { name: "Start", exact: true }).click();
      await expect(p).toHaveURL(/\/sessions\/(?!new$)[^/]+$/);
    }
    await spa(p, "/sessions");
    await expect(p.getByRole("list").getByRole("listitem").first()).toBeVisible();
    await expect(p.locator("[data-slot=badge][data-tone]").first()).toBeVisible();
  },
  upload: async (p) => { await verified(p, "c@example.com"); await openUpload(p); await expect(p.getByLabel("Change goal")).toBeVisible(); },
  "interview-new": async (p) => { await verified(p, "d@example.com"); await p.getByRole("link", { name: /Start AI Interview/ }).click(); await expect(p).toHaveURL(/interviews\/new/); await expect(p.getByRole("combobox", { name: "Voice" })).toBeVisible(); },
  session: async (p) => {
    await verified(p, "e@example.com");
    await openUpload(p);
    await p.getByLabel("Change goal").fill("Walk more");
    await p.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
    await p.getByRole("button", { name: "Start", exact: true }).click();
    await expect(p).toHaveURL(/\/sessions\/(?!new$)[^/]+$/);
    await expect(p.getByRole("button", { name: "Delete session" })).toBeVisible();
  },
  "session-delete-dialog": async (p) => {
    await SIGNED_IN.session(p);
    await p.getByRole("button", { name: "Delete session" }).click();
    await expect(p.getByRole("alertdialog")).toBeVisible();
  },
  settings: async (p) => { await verified(p, "f@example.com"); await accountMenu(p, "Settings"); await expect(p.getByRole("heading", { name: "Settings" })).toBeVisible(); },
  "settings-secret-dialog": async (p) => {
    await SIGNED_IN.settings(p);
    await p.getByRole("button", { name: "Create API key" }).click();
    await expect(p.getByRole("dialog")).toBeVisible();
  },
  "account-menu-open": async (p) => { await verified(p, "g@example.com"); await p.getByRole("button", { name: "Account menu" }).click(); await expect(p.getByRole("menuitem", { name: "Settings" })).toBeVisible(); },
};

const SCREENS = { ...SIGNED_OUT, ...SIGNED_IN };

for (const scheme of ["light", "dark"]) {
  test.describe(`${scheme} scheme`, () => {
    test.use({ colorScheme: scheme });
    for (const [name, go] of Object.entries(SCREENS)) {
      test(`${name}: screenshot + axe`, async ({ page }) => {
        const csp = await watchCsp(page);
        await go(page);
        await wait(page);
        expect(await page.evaluate(() => matchMedia("(prefers-color-scheme: dark)").matches)).toBe(scheme === "dark");
        await shotTo(page, `${scheme}-${name}`);
        const todo = TODO[`${name}@${scheme}`];
        const bad = await axeGate(page);
        if (todo) {
          test.info().annotations.push({ type: "axe-waived", description: `${todo}: ${bad.length} violation(s)` });
        } else {
          expect(bad, `axe ${scheme} ${name}`).toEqual([]);
        }
        expect(await csp.all()).toEqual([]);
      });
    }

    test("mobile 390px: shell + chooser + sample", async ({ browser }) => {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: scheme, baseURL: test.info().project.use.baseURL });
      const page = await ctx.newPage();
      for (const r of ["/login", "/sample"]) {
        await page.goto(r);
        await wait(page);
        await shotTo(page, `${scheme}-mobile-${r.replace(/\W/g, "_")}`);
        const bad = await axeGate(page);
        if (!TODO[`mobile${r}@${scheme}`]) expect(bad, `axe ${scheme} mobile ${r}`).toEqual([]);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
      }
      // Sample coded-transcript dialog at phone width (full-screen native dialog).
      await page.getByRole("button", { name: "Open coded transcript" }).click();
      await expect(page.locator("dialog[open]")).toBeVisible();
      await shotTo(page, `${scheme}-mobile-sample-transcript-dialog`);
      const dlgBad = await axeGate(page);
      expect(dlgBad, `axe ${scheme} mobile transcript dialog`).toEqual([]);
      await ctx.close();
    });
  });
}
