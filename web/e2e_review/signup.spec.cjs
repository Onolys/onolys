const { test, expect } = require("@playwright/test");
const { shot, collect, field, signUp, spa, navLinks, hasHScroll, PW } = require("./helpers.cjs");

const create = (page) => page.getByRole("button", { name: "Create account" });

test.describe("signup", () => {
  test("weak (<8) and whitespace-only passwords are rejected with a message", async ({ page }) => {
    await page.goto("/signup");
    await field(page, "Email").fill("ok@example.com");
    for (const pw of ["short", "1234567", "      "]) {
      await field(page, "Password").fill(pw);
      await create(page).click();
      await expect(page.getByText(/at least 8 characters for your password/i)).toBeVisible();
      await expect(page).toHaveURL(/\/signup/);
    }
    await shot(page, "signup-weak");
  });

  test("E4: empty form tells the user the email is missing", async ({ page }) => {
    test.fail(true, "E4: empty submit only reports the password rule, nothing about email");
    await page.goto("/signup");
    await create(page).click();
    await expect(page.getByText(/enter your email|email is required/i)).toBeVisible();
  });

  test("E4b: valid password + empty email shows an email error and creates no account", async ({ page }) => {
    test.fail(true, "E4b/W11: empty email is sent to the auth service (fake: account '' is created, user lands on /verify-email)");
    await page.goto("/signup");
    await field(page, "Password").fill(PW);
    await create(page).click();
    await page.waitForTimeout(600);
    await expect(page).toHaveURL(/\/signup/);
    await expect(page.getByRole("alert")).toBeVisible();
    await shot(page, "signup-empty-email");
  });

  test("E5: malformed email ('foo', 'a@b') is rejected before an account is created", async ({ page }) => {
    test.fail(true, "E5: fake auth accepts any string; no client-side format check (real Firebase rejects, UX untested)");
    for (const e of ["foo", "a@b"]) {
      await signUp(page, e);
      await expect(page).toHaveURL(/\/signup/);
    }
  });

  test("E6: error fields are programmatically marked invalid (aria-invalid) when validation fails", async ({ page }) => {
    test.fail(true, "E6: no aria-invalid on any field");
    await page.goto("/signup");
    await field(page, "Password").fill("short");
    await create(page).click();
    await expect(page.locator("[aria-invalid=true]")).not.toHaveCount(0);
  });

  test("existing email (any case) shows 'already exists' with a Log in link", async ({ page }) => {
    await signUp(page, "dup@example.com");
    await page.locator("main").getByRole("button", { name: "Sign out" }).click();
    await spa(page, "/signup");
    await field(page, "Email").fill("DUP@example.com");
    await field(page, "Password").fill(PW);
    await create(page).click();
    await expect(page.getByText(/already exists/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /log in instead/i })).toBeVisible();
    await shot(page, "signup-existing");
  });

  test("double click and Enter key create one account and land on /verify-email", async ({ page }) => {
    const c = collect(page);
    await page.goto("/signup");
    await field(page, "Email").fill("dbl@example.com");
    await field(page, "Password").fill(PW);
    await create(page).dblclick();
    await expect(page).toHaveURL(/verify-email/);
    expect(c.pageerrors).toEqual([]);
    await page.locator("main").getByRole("button", { name: "Sign out" }).click();
    await spa(page, "/signup");
    await field(page, "Email").fill("enter@example.com");
    await field(page, "Password").fill(PW);
    await field(page, "Password").press("Enter");
    await expect(page).toHaveURL(/verify-email/);
  });

  test("uppercase + surrounding whitespace email is normalised; unicode accepted", async ({ page }) => {
    await signUp(page, "Case@Example.com ");
    await expect(page.locator("main").getByText("case@example.com")).toBeVisible();
    await page.locator("main").getByRole("button", { name: "Sign out" }).click();
    await spa(page, "/signup");
    await field(page, "Email").fill("üser+tag@exämple.com");
    await field(page, "Password").fill("pässwörd😀1");
    await create(page).click();
    await expect(page.locator("main").getByText("üser+tag@exämple.com")).toBeVisible();
  });

  test("E7: a very long (254 char) email does not cause horizontal scroll on the verify page", async ({ page }) => {
    test.fail(true, "E7: long address overflows; buttons stretch off screen");
    await signUp(page, `${"a".repeat(240)}@example.com`);
    await expect(page).toHaveURL(/verify-email/);
    await shot(page, "signup-long-email");
    expect(await hasHScroll(page)).toBe(false);
  });

  test.describe("unverified state", () => {
    test("shows verify page, resend has a cooldown, sign out returns to /login", async ({ page }) => {
      await signUp(page, "unv@example.com");
      await expect(page.getByRole("heading", { name: "Verify your email" })).toBeVisible();
      await shot(page, "unverified");
      await page.getByRole("button", { name: "Resend email" }).click();
      await expect(page.getByText("Verification email sent.")).toBeVisible();
      await expect(page.getByRole("button", { name: /Resend in \d+s/ })).toBeDisabled();
      await page.locator("main").getByRole("button", { name: "Sign out" }).click();
      await expect(page).toHaveURL(/\/login/);
    });

    test("protected routes redirect to /verify-email (next preserved); login/signup redirect there too", async ({ page }) => {
      await signUp(page, "unv2@example.com");
      await spa(page, "/sessions/new");
      await expect(page).toHaveURL(/verify-email\?next=%2Fsessions%2Fnew/);
      await spa(page, "/settings");
      await expect(page).toHaveURL(/verify-email\?next=%2Fsettings/);
      await spa(page, "/login");
      await expect(page).toHaveURL(/verify-email/);
    });

    test("E1b/W1: unverified header offers only account-safe links", async ({ page }) => {
      await signUp(page, "unv3@example.com");
      const links = await navLinks(page);
      for (const t of ["Sessions", "New session", "Settings"]) expect(links).not.toContain(t);
    });

    test("verifying lands on the dashboard (next restored)", async ({ page }) => {
      await signUp(page, "unv4@example.com");
      await spa(page, "/sessions/new");
      await page.getByRole("button", { name: "I've verified" }).click();
      await expect(page.getByRole("heading", { name: "New session" })).toBeVisible();
    });
  });
});
