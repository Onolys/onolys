const { test, expect, devices } = require("@playwright/test");
const { shot, FIX, signUp, spa, hasHScroll } = require("./helpers.cjs");

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { defaultBrowserType, ...iphone } = devices["iPhone 13"]; // run on chromium (only chromium is installed)
test.use({ ...iphone, deviceScaleFactor: 1 });

const PUBLIC = ["/login", "/signup", "/sample-report", "/nope", "/auth/action?mode=resetPassword&oobCode=x"];

test.describe("mobile (iPhone 13 viewport)", () => {
  for (const r of PUBLIC) {
    test(`signed-out ${r}: no horizontal scroll`, async ({ page }) => {
      await page.goto(r);
      await page.waitForSelector("h1");
      await shot(page, `m-${r.replace(/[^a-z0-9]/gi, "_")}`);
      expect(await hasHScroll(page)).toBe(false);
    });
  }

  test("E20: header nav fits in at most two rows on a phone", async ({ page }) => {
    await page.goto("/login");
    const box = await page.locator("header").boundingBox();
    expect(box.height).toBeLessThan(130);
  });

  test("verify-email, dashboard, new session, session, report, settings, interview: no horizontal scroll", async ({ page }) => {
    await signUp(page, "m@example.com");
    await shot(page, "m-verify");
    expect(await hasHScroll(page), "verify-email").toBe(false);
    await page.getByRole("button", { name: "I've verified" }).click();
    await expect(page.getByRole("heading", { name: "Sessions" })).toBeVisible();
    await shot(page, "m-dashboard");
    expect(await hasHScroll(page), "dashboard").toBe(false);
    await page.locator("header nav a", { hasText: "New session" }).click();
    await shot(page, "m-new-session");
    expect(await hasHScroll(page), "new session").toBe(false);
    await page.getByLabel("Change goal").fill("Walk more");
    await page.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
    await page.getByRole("button", { name: "Start", exact: true }).click();
    await expect(page.getByRole("button", { name: "This is the clinician" }).first()).toBeVisible({ timeout: 20_000 });
    await shot(page, "m-session-speakers");
    expect(await hasHScroll(page), "session/speaker gate").toBe(false);
    await page.getByRole("button", { name: "This is the clinician" }).first().click();
    await expect(page.getByRole("status")).toContainText("Coding the session", { timeout: 30_000 });
    await expect(page.getByRole("link", { name: "View report" })).toBeVisible({ timeout: 30_000 });
    await page.getByRole("link", { name: "View report" }).click();
    await expect(page.getByRole("heading", { name: "Scorecard" })).toBeVisible();
    await expect(page.getByText(/Difference|Where Onolys disagrees/)).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "You", exact: true })).toHaveCount(0);
    await shot(page, "m-report");
    expect(await hasHScroll(page), "report").toBe(false);
    await page.locator("header nav a", { hasText: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await shot(page, "m-settings");
    expect(await hasHScroll(page), "settings").toBe(false);
    await spa(page, "/interviews/new");
    await page.waitForTimeout(800);
    await shot(page, "m-interview-new");
    expect(await hasHScroll(page), "interview new").toBe(false);
  });

  test("E7m: 254-char email on verify page does not scroll sideways on a phone", async ({ page }) => {
    await signUp(page, `${"a".repeat(240)}@example.com`);
    await expect(page).toHaveURL(/verify-email/);
    expect(await hasHScroll(page)).toBe(false);
  });
});
