import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { here, renderApp } from "../../test/renderApp";
import { createFakeAuthService } from "../fakeService";
import { appHosts, resolveContinue } from "./AuthAction";

const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });

async function svc(verified = false) {
  const service = createFakeAuthService();
  await service.signUp("a@clinic.org", "password1");
  await service.signOut();
  if (verified) service.markVerified("a@clinic.org");
  return service;
}

describe("/auth/action verifyEmail", () => {
  it("does not apply the code on load, only on click (link scanners)", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyEmail", "a@clinic.org");
    renderApp(`/auth/action?mode=verifyEmail&oobCode=${code}&apiKey=AQ.bad`, { service });
    await h1("Verify your email");
    expect(service.calls.emailVerifications).toBe(0);
    await userEvent.setup().click(screen.getByRole("button", { name: "Verify my email" }));
    await h1("Email verified");
    expect(service.calls.emailVerifications).toBe(1);
  });

  it("continues to the same-origin continueUrl path", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyEmail", "a@clinic.org");
    const cont = encodeURIComponent(`${window.location.origin}/login`);
    const { router } = renderApp(`/auth/action?mode=verifyEmail&oobCode=${code}&continueUrl=${cont}`, { service });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Verify my email" }));
    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await waitFor(() => expect(here(router)).toBe("/login"));
  });

  it("renders for a signed-in unverified user and flips emailVerified", async () => {
    const service = createFakeAuthService();
    service.signedInAs("a@clinic.org", { verified: false });
    const code = service.issueActionCode("verifyEmail", "a@clinic.org");
    renderApp(`/auth/action?mode=verifyEmail&oobCode=${code}`, { service });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Verify my email" }));
    await h1("Email verified");
    expect((await service.refreshUser())?.emailVerified).toBe(true);
  });

  it("explains an invalid/expired code and offers a new link (log in when signed out)", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyEmail", "a@clinic.org", { expired: true });
    renderApp(`/auth/action?mode=verifyEmail&oobCode=${code}`, { service });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Verify my email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid, has expired, or was already used");
    expect(screen.getByRole("link", { name: /new verification email/ })).toHaveAttribute("href", "/login");
    // the dead code is no longer offered again (E14)
    expect(screen.queryByRole("button", { name: "Verify my email" })).toBeNull();
    expect(screen.queryByText(/Confirm your email address/)).toBeNull();
  });

  it("links to /verify-email for a new link when signed in", async () => {
    const service = createFakeAuthService();
    service.signedInAs("a@clinic.org", { verified: false });
    renderApp("/auth/action?mode=verifyEmail&oobCode=nope", { service, user: { email: "a@clinic.org", verified: false } });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Verify my email" }));
    expect(await screen.findByRole("link", { name: "Get a new verification email" })).toHaveAttribute("href", "/verify-email");
  });

  it("shows a generic error for other failures", async () => {
    const service = await svc();
    vi.spyOn(service, "applyEmailVerification").mockRejectedValue({ code: "auth/network-request-failed" });
    renderApp("/auth/action?mode=verifyEmail&oobCode=x", { service });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Verify my email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
  });
});

describe("/auth/action pre-check failures and already verified (FX17)", () => {
  it("verifyEmail: a signed-in verified user sees Already verified + Continue, not invalid-link copy", async () => {
    const service = createFakeAuthService();
    service.signedInAs("a@clinic.org", { verified: true });
    renderApp("/auth/action?mode=verifyEmail&oobCode=used", { service, user: { email: "a@clinic.org", verified: true } });
    await h1("Already verified");
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
    expect(screen.queryByText(/invalid/)).toBeNull();
  });

  it("resetPassword: a network failure of the pre-check shows the network message and Try again, then recovers", async () => {
    const service = await svc();
    const code = service.issueActionCode("resetPassword", "a@clinic.org");
    const spy = vi.spyOn(service, "verifyPasswordResetCode").mockRejectedValueOnce({ code: "auth/network-request-failed" });
    renderApp(`/auth/action?mode=resetPassword&oobCode=${code}`, { service });
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
    expect(screen.queryByText(/Reset link expired/)).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    await h1("Choose a new password");
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it("change email: a network failure of the pre-check shows the network message and Try again", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyAndChangeEmail", "a@clinic.org", { newEmail: "b@clinic.org" });
    vi.spyOn(service, "checkEmailChangeCode").mockRejectedValueOnce({ code: "auth/network-request-failed" });
    renderApp(`/auth/action?mode=verifyAndChangeEmail&oobCode=${code}`, { service });
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    await h1("Confirm your new email");
  });
});

describe("resolveContinue", () => {
  const o = "https://app.onolys.com";
  it("allows same-origin paths", () => {
    expect(resolveContinue("https://app.onolys.com/verify-email?x=1", o)).toEqual({ kind: "path", path: "/verify-email?x=1" });
    expect(resolveContinue("/settings", o)).toEqual({ kind: "path", path: "/settings" });
  });
  it("allows only configured app hosts as external (FX34)", () => {
    expect(resolveContinue("https://evil.example/verify-email", o)).toEqual({ kind: "path", path: "/" });
    expect(appHosts({ VITE_APP_HOSTS: " Staging.Example , other.example", VITE_FIREBASE_AUTH_DOMAIN: "auth.example" })).toEqual(
      new Set(["staging.example", "other.example", "auth.example"]),
    );
    expect(resolveContinue("https://onolys-app-staging.web.app/verify-email", o, new Set(["onolys-app-staging.web.app"]))).toEqual({
      kind: "external",
      href: "https://onolys-app-staging.web.app/verify-email",
    });
  });
  it("falls back to the default app hosts when VITE_APP_HOSTS is unset or empty (FX34 follow-up)", () => {
    for (const v of [undefined, "", " , "]) {
      const hosts = appHosts({ VITE_APP_HOSTS: v, VITE_FIREBASE_AUTH_DOMAIN: "auth.example" });
      expect(hosts).toEqual(new Set(["auth.example", "app.onolys.com", "onolys-app.web.app", "onolys-app-staging.web.app"]));
    }
    expect(appHosts({ VITE_APP_HOSTS: "x.example" }).has("app.onolys.com")).toBe(false);
  });
  it("never redirects to other origins or odd schemes", () => {
    for (const bad of ["https://evil.example/x", "//evil.example", "javascript:alert(1)", "http://onolys-app.web.app/", "https://app.onolys.com@evil.example/", null, "http://[bad"]) {
      expect(resolveContinue(bad, o)).toEqual({ kind: "path", path: "/" });
    }
  });
});

describe("/auth/action resetPassword", () => {
  it("shows the email, rejects short passwords, then resets", async () => {
    const service = await svc();
    const code = service.issueActionCode("resetPassword", "a@clinic.org");
    const { router } = renderApp(`/auth/action?mode=resetPassword&oobCode=${code}`, { service });
    const user = userEvent.setup();
    await h1("Choose a new password");
    expect(screen.getByText("a@clinic.org")).toBeInTheDocument();
    await user.type(screen.getByLabelText("New password"), "short");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 8 characters");
    expect(service.calls.passwordResets).toBe(0);
    await user.clear(screen.getByLabelText("New password"));
    await user.type(screen.getByLabelText("New password"), "longenough1");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    await h1("Log in");
    expect(service.calls.passwordResets).toBe(1);
    expect(here(router)).toBe("/login");
    expect(within(screen.getByRole("main")).getByRole("status")).toHaveTextContent("Password updated");
    expect(screen.getByLabelText("Email")).toHaveValue("a@clinic.org");
    await service.signIn("a@clinic.org", "longenough1");
  });

  it("shows an expired message for a bad code", async () => {
    renderApp("/auth/action?mode=resetPassword&oobCode=bad");
    await h1("Reset link expired");
    expect(screen.getByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("/auth/action verifyAndChangeEmail", () => {
  it("shows the new email, applies only on click, then asks a signed-out user to log in with it", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyAndChangeEmail", "a@clinic.org", { newEmail: "b@clinic.org" });
    renderApp(`/auth/action?mode=verifyAndChangeEmail&oobCode=${code}&apiKey=AQ.bad`, { service });
    await h1("Confirm your new email");
    expect(screen.getByText("b@clinic.org")).toBeInTheDocument();
    expect(service.calls.emailChanges).toBe(0);
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirm new email" }));
    await h1("Email updated");
    expect(service.calls.emailChanges).toBe(1);
    expect(screen.getByRole("status")).toHaveTextContent("b@clinic.org");
    expect(screen.getByRole("status")).toHaveTextContent("Log in again with your new email");
    expect(within(screen.getByRole("main")).getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    await service.signIn("b@clinic.org", "password1");
  });

  it("explains an invalid/expired code without offering to apply it", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyAndChangeEmail", "a@clinic.org", { newEmail: "b@clinic.org", expired: true });
    renderApp(`/auth/action?mode=verifyAndChangeEmail&oobCode=${code}`, { service });
    await h1("Link expired");
    expect(screen.getByRole("alert")).toHaveTextContent("invalid, has expired, or was already used");
    expect(screen.queryByRole("button", { name: "Confirm new email" })).toBeNull();
    expect(service.calls.emailChanges).toBe(0);
  });

  it("shows an error when applying fails with an expired code", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyAndChangeEmail", "a@clinic.org", { newEmail: "b@clinic.org" });
    renderApp(`/auth/action?mode=verifyAndChangeEmail&oobCode=${code}`, { service });
    vi.spyOn(service, "applyEmailChange").mockRejectedValue({ code: "auth/expired-action-code" });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Confirm new email" }));
    await h1("Link expired");
  });

  it("shows a generic error for other apply failures and keeps the button", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyAndChangeEmail", "a@clinic.org", { newEmail: "b@clinic.org" });
    renderApp(`/auth/action?mode=verifyAndChangeEmail&oobCode=${code}`, { service });
    vi.spyOn(service, "applyEmailChange").mockRejectedValue({ code: "auth/network-request-failed" });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Confirm new email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Can't reach the server");
    expect(screen.getByRole("button", { name: "Confirm new email" })).toBeInTheDocument();
  });

  it("when still signed in, offers Continue to the safe continueUrl", async () => {
    const service = await svc();
    const code = service.issueActionCode("verifyAndChangeEmail", "a@clinic.org", { newEmail: "b@clinic.org" });
    vi.spyOn(service, "applyEmailChange").mockResolvedValue({ signedIn: true });
    const cont = encodeURIComponent(`${window.location.origin}/login`);
    const { router } = renderApp(`/auth/action?mode=verifyAndChangeEmail&oobCode=${code}&continueUrl=${cont}`, { service });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Confirm new email" }));
    await h1("Email updated");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(here(router)).toBe("/login"));
  });
});

describe("/auth/action recoverEmail", () => {
  it("shows the restored email, applies only on click, then suggests a password reset", async () => {
    const service = await svc();
    const code = service.issueActionCode("recoverEmail", "a@clinic.org", { previousEmail: "old@clinic.org" });
    renderApp(`/auth/action?mode=recoverEmail&oobCode=${code}`, { service });
    await h1("Restore your email");
    expect(screen.getByText("old@clinic.org")).toBeInTheDocument();
    expect(service.calls.emailChanges).toBe(0);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Restore this email" }));
    await h1("Email restored");
    expect(service.calls.emailChanges).toBe(1);
    expect(screen.getByRole("status")).toHaveTextContent("old@clinic.org");
    expect(service.calls.resets).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Reset my password" }));
    expect(await screen.findByText(/reset email sent/i)).toBeInTheDocument();
    expect(service.calls.resets).toEqual(["old@clinic.org"]);
    expect(within(screen.getByRole("main")).getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
  });

  it("explains an invalid/expired code", async () => {
    renderApp("/auth/action?mode=recoverEmail&oobCode=bad");
    await h1("Link expired");
    expect(screen.getByRole("alert")).toHaveTextContent("invalid, has expired, or was already used");
    expect(screen.queryByRole("button", { name: "Restore this email" })).toBeNull();
  });

  it("shows an error when the password reset email fails", async () => {
    const service = await svc();
    const code = service.issueActionCode("recoverEmail", "a@clinic.org", { previousEmail: "old@clinic.org" });
    renderApp(`/auth/action?mode=recoverEmail&oobCode=${code}`, { service });
    vi.spyOn(service, "sendPasswordReset").mockRejectedValue({ code: "auth/too-many-requests" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Restore this email" }));
    await user.click(await screen.findByRole("button", { name: "Reset my password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});

describe("/auth/action revertSecondFactorAddition", () => {
  it("is treated as not valid (MFA is not used) and never applies a code", async () => {
    const service = await svc();
    renderApp("/auth/action?mode=revertSecondFactorAddition&oobCode=x", { service });
    await h1("This link isn't valid");
    expect(screen.getByText(/two-step verification isn't used/i)).toBeInTheDocument();
    expect(service.calls.emailChanges).toBe(0);
  });
});

describe("/auth/action other", () => {
  it.each(["/auth/action", "/auth/action?mode=other&oobCode=x", "/auth/action?mode=verifyEmail", "/auth/action?mode=resetPassword", "/auth/action?mode=recoverEmail", "/auth/action?mode=verifyAndChangeEmail"])(
    "%s is not valid",
    async (path) => {
      renderApp(path);
      await h1("This link isn't valid");
    },
  );
});
