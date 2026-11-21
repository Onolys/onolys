// @live: needs Firestore emulator + api (stub adapters, fake auth). Excluded by default; run with E2E_MODE=live.
const { test, expect } = require("@playwright/test");
const { shot, collect, FIX, signUpVerified, spa } = require("./helpers.cjs");

test.describe("live-ish backend @live", () => {
  test("@live upload -> transcribe -> speaker -> rating -> report against the real api (stub adapters)", async ({ page }) => {
    test.fail(true, "E22: local FakeBlobStore PUT is blocked by api CORS preflight (400), so the upload fails and the worker never runs");
    const c = collect(page);
    await signUpVerified(page, `live-${Date.now()}@example.com`);
    await page.locator("header nav a", { hasText: "New session" }).click();
    await page.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
    await page.getByRole("button", { name: "Start", exact: true }).click();
    await expect(page).toHaveURL(/\/sessions\/(?!new$)[^/]+$/);
    await expect(page.getByRole("button", { name: "This is the clinician" }).first()).toBeVisible({ timeout: 40_000 });
    await shot(page, "live-speakers");
    await page.getByRole("button", { name: "This is the clinician" }).first().click();
    await page.locator("#rating-globals-cct-score").selectOption({ index: 4 });
    await page.locator("#rating-change_goal").fill("Walk more");
    await page.getByRole("button", { name: "Submit rating" }).click();
    await expect(page.getByRole("link", { name: "View report" })).toBeVisible({ timeout: 60_000 });
    await page.getByRole("link", { name: "View report" }).click();
    await expect(page.getByRole("heading", { name: "Scorecard" })).toBeVisible();
    await shot(page, "live-report");
    expect(c.pageerrors).toEqual([]);
  });

  test("@live an unknown session id shows an error alert (live api; mock mode hangs, see E21)", async ({ page }) => {
    await signUpVerified(page, `live-miss-${Date.now()}@example.com`);
    await spa(page, "/sessions/does_not_exist");
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
  });
});
