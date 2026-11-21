const { test, expect } = require("@playwright/test");
const { shot, collect, navLinks, path_ } = require("./helpers.cjs");

const PROTECTED = ["/", "/sessions/new", "/sessions/abc123", "/sessions/abc123/reports/1", "/interviews/new", "/interviews/xyz", "/settings"];

test.describe("signed-out gating", () => {
  test("E1/W1: header does not offer Sessions / New session / Settings when signed out", async ({ page }) => {
    test.fail(true, "E1/W1: Layout always renders the full nav");
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
    await shot(page, "so-login");
    const links = await navLinks(page);
    for (const t of ["Sessions", "New session", "Settings"]) expect(links).not.toContain(t);
  });

  for (const route of PROTECTED) {
    test(`deep link ${route} bounces to /login with next and shows no protected UI`, async ({ page }) => {
      const c = collect(page);
      await page.goto(route);
      await expect(page).toHaveURL(/\/login/);
      if (route !== "/") expect(new URL(page.url()).searchParams.get("next")).toBe(route);
      await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
      await expect(page.getByRole("heading", { name: /New session|Settings|^Session$/ })).toHaveCount(0);
      expect(c.pageerrors).toEqual([]);
    });
  }

  test("auth-loading state never shows protected content (sampled right after navigation)", async ({ page }) => {
    const seen = new Set();
    await page.goto("/settings", { waitUntil: "commit" });
    for (let i = 0; i < 20; i++) {
      seen.add(await page.evaluate(() => document.querySelector("main")?.innerText.replace(/\s+/g, " ").slice(0, 40) ?? "").catch(() => ""));
      await page.waitForTimeout(30);
    }
    for (const s of seen) expect(s).not.toMatch(/^Settings|API key|^Sessions/);
  });

  test("clicking protected nav links signed out ends on /login (with next); Sample report is public", async ({ page }) => {
    await page.goto("/login");
    await page.locator("header nav a", { hasText: "Settings" }).click();
    await expect(page).toHaveURL(/\/login\?next=%2Fsettings/);
    await page.locator("header nav a", { hasText: "Sample report" }).click();
    await expect(page.getByRole("heading", { name: "Sample report" })).toBeVisible();
    await shot(page, "so-sample-report");
  });

  test("back button after bounce never reveals protected UI; reload keeps next", async ({ page }) => {
    await page.goto("/login");
    await page.goto("/settings");
    await expect(page).toHaveURL(/login/);
    await page.goBack();
    await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
    await page.goto("/login?next=/sessions/new");
    await page.reload();
    expect(path_(page)).toBe("/login?next=/sessions/new");
  });

  test("/verify-email signed out goes to /login; unknown route shows 404 page", async ({ page }) => {
    await page.goto("/verify-email");
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/nope");
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
    await shot(page, "so-404");
  });

  test("E2/W1: 404 page for signed-out users does not offer 'Back to your sessions'", async ({ page }) => {
    test.fail(true, "E2: NotFound copy/nav assumes signed-in user");
    await page.goto("/nope");
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
    await expect(page.getByText("Back to your sessions")).toHaveCount(0);
  });
});
