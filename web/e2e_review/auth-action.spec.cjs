const { test, expect } = require("@playwright/test");
const { shot, signUp, spa } = require("./helpers.cjs");

// Valid oobCodes cannot be minted from the browser (fake service keeps them in memory), so only invalid-code
// paths are covered here. Valid-code paths (W8, W9, W21) are covered by src/auth/pages unit tests.
const A = "/auth/action";
const H = (page, name) => expect(page.getByRole("heading", { name })).toBeVisible();

test.describe("/auth/action", () => {
  for (const q of ["", "?mode=verifyEmail", "?mode=resetPassword", "?oobCode=x", "?mode=bogus&oobCode=x", "?mode=VerifyEmail&oobCode=x"]) {
    test(`incomplete/unknown link ${q || "(no params)"} -> 'This link isn't valid'`, async ({ page }) => {
      await page.goto(A + q);
      await H(page, "This link isn't valid");
      await expect(page.getByRole("link", { name: "Go to log in" })).toBeVisible();
    });
  }

  test("revertSecondFactorAddition explains nothing to undo", async ({ page }) => {
    await page.goto(`${A}?mode=revertSecondFactorAddition&oobCode=x`);
    await expect(page.getByText(/nothing to undo/)).toBeVisible();
  });

  test("bogus verifyEmail code: nothing consumed on load; click shows invalid/expired message (signed out)", async ({ page }) => {
    await page.goto(`${A}?mode=verifyEmail&oobCode=bogus`);
    await H(page, "Verify your email");
    await page.getByRole("button", { name: "Verify my email" }).click();
    await expect(page.getByText(/invalid, has expired, or was already used/)).toBeVisible();
    await expect(page.getByRole("link", { name: /Log in to get a new verification email/ })).toBeVisible();
    await shot(page, "action-verify-bogus");
  });

  test("E14: after an invalid verify code the 'Confirm your email address... Verify my email' prompt is not still offered", async ({ page }) => {
    await page.goto(`${A}?mode=verifyEmail&oobCode=bogus`);
    await page.getByRole("button", { name: "Verify my email" }).click();
    await expect(page.getByText(/invalid, has expired/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Verify my email" })).toHaveCount(0);
  });

  test("bogus resetPassword code -> 'Reset link expired' with request-new-link", async ({ page }) => {
    await page.goto(`${A}?mode=resetPassword&oobCode=bogus`);
    await H(page, "Reset link expired");
    await expect(page.getByRole("link", { name: "Request a new reset link" })).toBeVisible();
    await shot(page, "action-reset-bogus");
  });

  for (const mode of ["verifyAndChangeEmail", "recoverEmail"]) {
    test(`bogus ${mode} code -> 'Link expired'`, async ({ page }) => {
      await page.goto(`${A}?mode=${mode}&oobCode=bogus`);
      await H(page, "Link expired");
    });
  }

  test("continueUrl to an unknown host is never followed", async ({ page }) => {
    const hits = [];
    await page.route(/^https?:\/\/evil\.com/, (r) => { hits.push(r.request().url()); r.abort(); });
    await page.goto(`${A}?mode=verifyEmail&oobCode=bogus&continueUrl=https://evil.com`);
    await page.getByRole("button", { name: "Verify my email" }).click();
    await page.waitForTimeout(500);
    expect(hits).toEqual([]);
  });

  test("signed-in unverified user: invalid verify code offers 'Get a new verification email'", async ({ page }) => {
    await signUp(page, "act@example.com");
    await spa(page, `${A}?mode=verifyEmail&oobCode=bogus`);
    await page.getByRole("button", { name: "Verify my email" }).click();
    await expect(page.getByRole("link", { name: "Get a new verification email" })).toBeVisible();
  });

  test("E1c/W1: auth action page header shows no protected nav", async ({ page }) => {
    await page.goto(`${A}?mode=resetPassword&oobCode=bogus`);
    await H(page, "Reset link expired");
    await expect(page.locator("header nav a", { hasText: "Settings" })).toHaveCount(0);
  });
});
