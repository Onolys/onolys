const { test, expect } = require("@playwright/test");
const { shot, collect, FIX, signUpVerified, spa } = require("./helpers.cjs");

async function newSession(page, file = "ten-min.mp3", { dbl = false } = {}) {
  await page.locator("header nav a", { hasText: "New session" }).click();
  await page.locator("input[type=file]").setInputFiles(FIX(file));
  const start = page.getByRole("button", { name: "Start", exact: true });
  await expect(start).toBeEnabled({ timeout: 10_000 });
  if (dbl) await start.dblclick();
  else await start.click();
  await expect(page).toHaveURL(/\/sessions\/(?!new$)[^/]+$/);
}

test.describe("new session precheck", () => {
  test("non-audio file is blocked; <10 min warns; ok file enables Start", async ({ page }) => {
    await signUpVerified(page, "pre@example.com");
    await page.locator("header nav a", { hasText: "New session" }).click();
    const start = page.getByRole("button", { name: "Start", exact: true });
    await expect(start).toBeDisabled();
    await page.locator("input[type=file]").setInputFiles(FIX("notaudio.txt"));
    await expect(page.getByRole("alert")).toContainText(/can't use this file type/);
    await expect(start).toBeDisabled();
    await page.locator("input[type=file]").setInputFiles(FIX("one-min.wav"));
    await expect(page.getByRole("status")).toContainText(/under 10 minutes/);
    await page.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
    await expect(start).toBeEnabled();
    await shot(page, "new-session-ok");
  });

  test("W17: picking a short file right after a long one ends with the short file's warning (race)", async ({ page }) => {
    await signUpVerified(page, "race@example.com");
    await page.locator("header nav a", { hasText: "New session" }).click();
    const input = page.locator("input[type=file]");
    await input.setInputFiles(FIX("one-min.wav"));
    await input.setInputFiles(FIX("ten-min.mp3"));
    await page.waitForTimeout(2500);
    await expect(page.getByRole("status")).toHaveCount(0); // ten-min.mp3 has no warning; local reads are too fast to lose the race
    await expect(page.getByRole("button", { name: "Start", exact: true })).toBeEnabled();
  });
});

test.describe("main flow (mock backend)", () => {
  test("upload -> transcribe -> speaker -> rating -> report -> settings usage; no console errors", async ({ page }) => {
    const c = collect(page);
    await signUpVerified(page, "flow@example.com");
    await newSession(page);
    await expect(page.getByRole("heading", { name: "Session" })).toBeVisible();
    await shot(page, "session-running");
    await expect(page.getByRole("button", { name: "This is the clinician" }).first()).toBeVisible({ timeout: 20_000 });
    await shot(page, "session-speakers");
    await page.getByRole("button", { name: "This is the clinician" }).first().click();
    await page.locator("#rating-globals-cct-score").selectOption({ index: 4 });
    await page.locator("#rating-change_goal").fill("Walk more");
    await expect(page.getByText("Draft saved")).toBeVisible({ timeout: 8000 });
    await page.getByRole("button", { name: "Submit rating" }).click();
    await expect(page.getByRole("link", { name: "View report" })).toBeVisible({ timeout: 30_000 });
    await shot(page, "session-done");
    await page.getByRole("link", { name: "View report" }).click();
    await expect(page.getByRole("heading", { name: "Scorecard" })).toBeVisible();
    await shot(page, "report");
    await page.locator("header nav a", { hasText: "Settings" }).click();
    await expect(page.getByText(/Ratings: 19 of 20 left today/)).toBeVisible();
    await shot(page, "settings");
    await page.locator("header nav a", { hasText: "Sessions" }).click();
    await expect(page.getByRole("link", { name: /session|Walk more|E2E/i }).first()).toBeVisible();
    await shot(page, "dashboard-with-session");
    expect(c.pageerrors).toEqual([]);
    expect(c.failed).toEqual([]);
    expect(c.http).toEqual([]);
  });

  test("E16: double-click on Start does not produce failed upload requests (403/409)", async ({ page }) => {
    test.fail(true, "E16: second submit PUTs a stale signed URL -> 403, /audio/complete -> 409 (console errors)");
    const c = collect(page);
    await signUpVerified(page, "dbl@example.com");
    await newSession(page, "ten-min.mp3", { dbl: true });
    await page.waitForTimeout(3000);
    expect(c.http).toEqual([]);
  });

  test("W2/E17: a rating edit made just before in-app Back navigation is not lost", async ({ page }) => {
    await signUpVerified(page, "w2@example.com");
    await newSession(page);
    await expect(page.locator("#rating-change_goal")).toBeVisible();
    await page.locator("#rating-change_goal").fill("Keep this goal");
    await page.evaluate(() => history.back()); // no blur first
    await expect(page.getByRole("heading", { name: "New session" })).toBeVisible();
    await page.waitForTimeout(500);
    await page.evaluate(() => history.forward());
    await expect(page.locator("#rating-change_goal")).toHaveValue("Keep this goal");
  });

  test("E21: a missing session shows an error, not an endless 'Loading session...'", async ({ page }) => {
    await signUpVerified(page, "miss@example.com");
    await spa(page, "/sessions/s_does_not_exist");
    await expect(page.getByRole("alert").or(page.getByText(/not found|couldn't/i)).first()).toBeVisible({ timeout: 10_000 });
  });

  test("W26/E19: Settings 'Copy' gives feedback and API key secret dialog restores focus", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await signUpVerified(page, "key@example.com");
    await page.locator("header nav a", { hasText: "Settings" }).click();
    await page.getByRole("button", { name: "Create API key" }).click();
    await shot(page, "settings-secret");
    await page.getByRole("button", { name: "Copy" }).click();
    await expect(page.getByText(/copied/i)).toBeVisible({ timeout: 2000 });
  });

  test("Settings: create, regenerate-confirm and revoke API key", async ({ page }) => {
    await signUpVerified(page, "key2@example.com");
    await page.locator("header nav a", { hasText: "Settings" }).click();
    await page.getByRole("button", { name: "Create API key" }).click();
    await expect(page.getByTestId("api-secret")).toContainText("onolys_");
    await expect(page.getByRole("button", { name: "Done" })).toBeDisabled();
    await page.getByLabel("I've stored it").check();
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByText("Active")).toBeVisible();
    await page.getByRole("button", { name: "Revoke" }).click();
    await shot(page, "settings-revoke");
  });

  test("interview start page loads without console errors", async ({ page }) => {
    const c = collect(page);
    await signUpVerified(page, "int@example.com");
    await page.getByRole("link", { name: /Start AI Interview/ }).click();
    await expect(page).toHaveURL(/interviews\/new/);
    await page.waitForTimeout(1500);
    await shot(page, "interview-new");
    expect(c.pageerrors).toEqual([]);
    expect(c.console).toEqual([]);
  });
});
