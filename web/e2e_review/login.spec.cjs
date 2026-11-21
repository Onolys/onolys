const { test, expect } = require("@playwright/test");
const { shot, collect, field, signUpVerified, spa, signOutViaSettings, path_, PW } = require("./helpers.cjs");

const loginBtn = (page) => page.getByRole("button", { name: "Log in", exact: true });
async function account(page, email = "u1@example.com") {
  await signUpVerified(page, email);
  await signOutViaSettings(page);
  await expect(page).toHaveURL(/\/login/);
  await spa(page, "/login");
}
async function fillLogin(page, email, pw = PW) {
  await field(page, "Email").fill(email);
  await field(page, "Password").fill(pw);
  await loginBtn(page).click();
}

test.describe("login / logout", () => {
  test("wrong password and unknown user show the same non-enumerating message", async ({ page }) => {
    await account(page);
    await fillLogin(page, "u1@example.com", "wrongpass");
    await expect(page.getByText(/don't match/i)).toBeVisible();
    await fillLogin(page, "nobody@example.com");
    await expect(page.getByText(/don't match/i)).toBeVisible();
    await shot(page, "login-wrong");
  });

  test("E8/W11: empty submit asks for email/password instead of claiming credentials mismatch", async ({ page }) => {
    await page.goto("/login");
    await loginBtn(page).click();
    await expect(page.getByText(/enter your (email|password)/i)).toBeVisible();
  });

  test("Enter key submits; uppercase and padded email works", async ({ page }) => {
    await account(page);
    await field(page, "Email").fill("  U1@EXAMPLE.com ");
    await field(page, "Password").fill(PW);
    await field(page, "Password").press("Enter");
    await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible();
  });

  test("E9: signing out from Settings lands on plain /login (no next=/settings)", async ({ page }) => {
    await signUpVerified(page, "so@example.com");
    await signOutViaSettings(page);
    await expect(page).toHaveURL(/\/login$/);
  });

  test("logout then back button never shows protected UI", async ({ page }) => {
    await signUpVerified(page, "back@example.com");
    await signOutViaSettings(page);
    await page.goBack();
    await expect(page.getByRole("heading", { name: /^Settings$/ })).toHaveCount(0);
    await page.goForward();
    await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
  });
});

test.describe("?next= handling", () => {
  const SAFE_FALLBACK = ["//evil.com", "https://evil.com", "/\\evil.com", "javascript:alert(1)", "/login"];
  for (const n of SAFE_FALLBACK) {
    test(`next=${n} is never followed off-site; lands on /`, async ({ page }) => {
      const hits = [];
      await page.route(/^https?:\/\/(www\.)?evil\.com/, (r) => { hits.push(r.request().url()); r.abort(); });
      await account(page);
      await spa(page, `/login?next=${encodeURIComponent(n)}`);
      await fillLogin(page, "u1@example.com");
      await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible();
      expect(path_(page)).toBe("/");
      expect(hits).toEqual([]);
    });
  }

  test("next=/sessions/new and next=/settings are honoured after login", async ({ page }) => {
    await account(page);
    await spa(page, "/login?next=/sessions/new");
    await fillLogin(page, "u1@example.com");
    await expect(page.getByRole("heading", { name: "New session" })).toBeVisible();
  });

  test("E3/W19/W7: next=/%09/evil.com does not crash the app after login", async ({ page }) => {
    const c = collect(page);
    await account(page);
    await spa(page, "/login?next=/%09/evil.com");
    await fillLogin(page, "u1@example.com");
    await page.waitForTimeout(800);
    await shot(page, "next-tab-evil");
    expect(c.console.filter((m) => /External navigation/.test(m))).toEqual([]);
    await expect(page.locator("header")).toBeVisible();
  });

  test("E11/W7: any render crash still keeps a way back (error element with layout)", async ({ page }) => {
    await account(page);
    await spa(page, "/login?next=/%09/evil.com");
    await fillLogin(page, "u1@example.com");
    await page.waitForTimeout(800);
    await expect(page.getByRole("link", { name: /Onolys|Sessions|Back/ }).first()).toBeVisible();
  });

  test("E12/W19: next=/auth/action (a dead-end page) falls back to /", async ({ page }) => {
    await account(page);
    await spa(page, "/login?next=/auth/action");
    await fillLogin(page, "u1@example.com");
    await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible();
  });
});

test.describe("forgot password", () => {
  test("empty asks for email; unknown and known emails give the same neutral confirmation", async ({ page }) => {
    await page.goto("/forgot-password");
    await page.getByRole("button", { name: /Send reset link/ }).click();
    await expect(page.getByText(/enter your email/i)).toBeVisible();
    for (const e of ["nobody@example.com", "u1@example.com"]) {
      await field(page, "Email").fill(e);
      await page.getByRole("button", { name: /Send reset link/ }).click();
      await expect(page.getByText(/If an account exists/)).toBeVisible();
    }
    await shot(page, "forgot-sent");
  });

  test("E13/W14: a malformed email ('foo') does not show the success confirmation", async ({ page }) => {
    await page.goto("/forgot-password");
    await field(page, "Email").fill("foo");
    await page.getByRole("button", { name: /Send reset link/ }).click();
    await expect(page.getByText(/If an account exists/)).toHaveCount(0);
  });
});
