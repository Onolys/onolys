// CSP smoke (PRD R9): the built mock app served by `vite preview` with the exact prod firebase.json CSP; zero violations required.
const { test, expect, devices } = require("@playwright/test");
const { FIX, signUpVerified, spa, accountMenu, openUpload } = require("./helpers.cjs");
const { watchCsp, expectStrictPolicy } = require("./csp-helpers.cjs");

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { defaultBrowserType, ...iphone } = devices["iPhone 13"];

async function newSession(page) {
  await openUpload(page);
  await page.getByLabel("Change goal").fill("Walk more");
  await page.locator("input[type=file]").setInputFiles(FIX("ten-min.mp3"));
  const start = page.getByRole("button", { name: "Start", exact: true });
  await expect(start).toBeEnabled({ timeout: 10_000 });
  await start.click();
  await expect(page).toHaveURL(/\/sessions\/(?!new$)[^/]+$/);
}

test.describe("CSP smoke: zero violations under the prod CSP", () => {
  test("the preview serves the strict prod policy and the listener catches a violation", async ({ page }) => {
    const csp = await watchCsp(page);
    await page.goto("/login");
    await expectStrictPolicy(page);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await csp.all()).toEqual([]);
    // control: a deliberate inline style / script must trip the listener, else the zero-violation gate below proves nothing
    await page.evaluate(() => {
      const s = document.createElement("style");
      s.textContent = "body{outline:1px solid red}";
      document.head.appendChild(s);
      document.body.setAttribute("style", "color:red");
    });
    await expect.poll(async () => (await csp.all()).length).toBeGreaterThan(0);
    expect((await csp.all()).join("\n")).toMatch(/style-src/);
  });

  test("signed-out shell, focus rings, 404, privacy", async ({ page }) => {
    const csp = await watchCsp(page);
    await page.goto("/login");
    for (let i = 0; i < 6; i++) await page.keyboard.press("Tab"); // focus rings on links/inputs/buttons
    await page.goto("/privacy");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.goto("/nope");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await csp.all()).toEqual([]);
  });

  test("account menu, settings secret dialog, native select, session DeleteDialog", async ({ page, context, browserName }) => {
    // Firefox/WebKit authorize clipboard writes through the Copy click itself.
    if (browserName === "chromium") await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const csp = await watchCsp(page);
    await signUpVerified(page, "csp@example.com");

    await page.getByRole("button", { name: "Account menu" }).click();
    await expect(page.getByRole("menuitem", { name: "Settings" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu")).toHaveCount(0); // let the exit animation finish before reopening
    await expect(page.getByRole("button", { name: "Account menu" })).toBeFocused(); // Escape returns focus
    await accountMenu(page, "Settings");
    await page.getByRole("button", { name: "Create API key" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Copy" }).click();
    await expect(page.getByText(/copied/i)).toBeVisible();
    await page.keyboard.press("Escape");
    await page.mouse.click(5, 5); // outside click
    await expect(page.getByRole("dialog")).toBeVisible(); // neither dismisses the one-time secret
    await page.getByRole("checkbox", { name: /stored it/i }).click();
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Regenerate" }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("alertdialog")).toHaveCount(0);

    await spa(page, "/sessions/new"); // native <select>: choose / change
    const lang = page.getByRole("combobox").first();
    await expect(lang).toBeVisible();
    const options = await lang.locator("option").evaluateAll((o) => o.map((x) => x.value));
    expect(options.length).toBeGreaterThan(1);
    await lang.selectOption(options[1]);
    await lang.selectOption(options[0]);

    await spa(page, "/interviews/new"); // native <select> (voice) on the interview picker: choose / change
    const voice = page.getByRole("combobox", { name: "Voice" });
    await expect(voice).toBeVisible();
    const voices = await voice.locator("option").evaluateAll((o) => o.map((x) => x.value));
    expect(voices.length).toBeGreaterThan(1);
    await voice.selectOption(voices[1]);
    await voice.selectOption(voices[0]);

    await spa(page, "/new");
    await newSession(page);
    await page.getByRole("button", { name: "Delete session" }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Delete session" })).toBeFocused();
    expect(await csp.all()).toEqual([]);
  });

  test("native coded-transcript dialog at mobile viewport: open, pointed scroll/highlight, focus return", async ({ browser }) => {
    const ctx = await browser.newContext({ ...iphone, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const csp = await watchCsp(page);
    await page.goto("/sample");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const opener = page.getByRole("button", { name: "Open coded transcript" });
    await opener.click();
    const dlg = page.locator("dialog[open]");
    await expect(dlg).toBeVisible();
    await dlg.getByRole("button", { name: "Close" }).click();
    await expect(dlg).toHaveCount(0);
    await expect(opener).toBeFocused();
    // pointed utterance: opens at that row, highlights it
    const link = page.getByRole("button", { name: /^Open utterance \d+$/ }).first();
    await link.scrollIntoViewIfNeeded();
    await link.click();
    await expect(page.locator("dialog[open] .hl")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(page.locator("dialog[open]")).toHaveCount(0);
    await expect(link).toBeFocused();
    expect(await csp.all()).toEqual([]);
    await ctx.close();
  });
});
