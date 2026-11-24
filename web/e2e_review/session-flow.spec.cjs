const { test, expect } = require("@playwright/test");
const { shot, collect, FIX, signUpVerified, spa, openUpload, accountMenu } = require("./helpers.cjs");

async function newSession(page, file = "ten-min.mp3", { dbl = false } = {}) {
  await openUpload(page);
  await page.getByLabel("Change goal").fill("Walk more");
  await page.locator("input[type=file]").setInputFiles(FIX(file));
  const start = page.getByRole("button", { name: "Start", exact: true });
  await expect(start).toBeEnabled({ timeout: 10_000 });
  if (dbl) await start.dblclick();
  else await start.click();
  await expect(page).toHaveURL(/\/sessions\/(?!new$)[^/]+$/);
}

test.describe("new session precheck", () => {
  test("non-audio file is blocked; <10 min warns; ok file + goal enables Start", async ({ page }) => {
    await signUpVerified(page, "pre@example.com");
    await openUpload(page);
    const start = page.getByRole("button", { name: "Start", exact: true });
    await expect(start).toBeDisabled();
    await page.locator("input[type=file]").setInputFiles(FIX("notaudio.txt"));
    await expect(page.getByRole("alert")).toContainText(/can't use this file type/);
    await expect(start).toBeDisabled();
    await page.locator("input[type=file]").setInputFiles(FIX("one-min.wav"));
    await expect(page.getByRole("status")).toContainText(/under 10 minutes/);
    await page.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
    await expect(start).toBeDisabled(); // the goal is still required
    await page.getByLabel("Change goal").fill("Walk more");
    await expect(start).toBeEnabled();
    await shot(page, "new-session-ok");
  });

});

test.describe("browser behaviours (mock backend)", () => {

  test("E16: double-click on Start does not produce failed upload requests (403/409)", async ({ page }) => {
    const c = collect(page);
    await signUpVerified(page, "dbl@example.com");
    await newSession(page, "ten-min.mp3", { dbl: true });
    await page.waitForTimeout(3000);
    expect(c.http).toEqual([]);
  });

  test("E21: a missing session shows an error, not an endless 'Loading session...'", async ({ page }) => {
    await signUpVerified(page, "miss@example.com");
    await spa(page, "/sessions/s_does_not_exist");
    await expect(page.getByRole("alert").or(page.getByText(/not found|couldn't/i)).first()).toBeVisible({ timeout: 10_000 });
  });

  test("W26/E19: Settings keeps account information and omits retired API controls", async ({ page }) => {
    await signUpVerified(page, "key@example.com");
    await accountMenu(page, "Settings");
    await expect(page.getByRole("region", { name: "Usage" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Account", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Create API key|Regenerate|Sign out/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /API docs/i })).toHaveCount(0);
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
