const { test, expect } = require("@playwright/test");
const { collect, field, signUp, spa, navLinks, PW } = require("./helpers.cjs");

const create = (page) => page.getByRole("button", { name: "Create account" });

test.describe("signup", () => {






  test("double click and Enter key create one account and land on /verify-email", async ({ page }) => {
    const c = collect(page);
    await page.goto("/signup");
    await field(page, "Email").fill("dbl@example.com");
    await field(page, "Password").fill(PW);
    await field(page, "Confirm password").fill(PW);
    await create(page).dblclick();
    await expect(page).toHaveURL(/verify-email/);
    expect(c.pageerrors).toEqual([]);
    await page.getByRole("button", { name: "Use a different email" }).click();
    await expect(page).toHaveURL(/\/signup/);
    await spa(page, "/signup");
    await field(page, "Email").fill("enter@example.com");
    await field(page, "Password").fill(PW);
    await field(page, "Confirm password").fill(PW);
    await field(page, "Password").press("Enter");
    await expect(page).toHaveURL(/verify-email/);
  });



  test.describe("unverified state", () => {

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
