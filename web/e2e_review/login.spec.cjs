const { test, expect } = require("@playwright/test");
const { shot, collect, field, emailFor, signUpVerified, spa, signOutViaSettings, path_, PW } = require("./helpers.cjs");

const loginBtn = (page) => page.getByRole("button", { name: "Log in", exact: true });
async function account(page, email = "u1@example.com") {
  await signUpVerified(page, email);
  await signOutViaSettings(page);
  await expect(page).toHaveURL(/\/login/);
  await spa(page, "/login");
}
async function fillLogin(page, email, pw = PW) {
  await field(page, "Email").fill(emailFor(page, email));
  await field(page, "Password").fill(pw);
  await loginBtn(page).click();
}

test.describe("login / logout", () => {



  // Known issue in @onolys/common 0.4.0: the SDK reports the sign-out after the app has navigated to /login, and the guard's
  // redirect then wins, so the user lands on /login?next=%2Fsettings. The old in-memory fake auth hid it. Delete `test.fail()` once fixed.
  test("E9: signing out from Settings lands on plain /login (no next=/settings)", async ({ page }) => {
    test.fail();
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
  const SAFE_FALLBACK = ["//evil.com", "javascript:alert(1)"];
  for (const n of SAFE_FALLBACK) {
    test(`next=${n} is never followed off-site; lands on /new`, async ({ page }) => {
      const hits = [];
      await page.route(/^https?:\/\/(www\.)?evil\.com/, (r) => { hits.push(r.request().url()); r.abort(); });
      await account(page);
      await spa(page, `/login?next=${encodeURIComponent(n)}`);
      await fillLogin(page, "u1@example.com");
      await expect(page.getByRole("heading", { name: /^Welcome/ })).toBeVisible();
      expect(path_(page)).toBe("/new");
      expect(hits).toEqual([]);
    });
  }


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

});

test.describe("forgot password", () => {

});
