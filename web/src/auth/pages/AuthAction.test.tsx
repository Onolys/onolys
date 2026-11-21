import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { here, renderApp } from "../../test/renderApp";
import { createFakeAuthService } from "../fakeService";
import { resolveContinue } from "./AuthAction";

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

describe("resolveContinue", () => {
  const o = "https://app.onolys.com";
  it("allows same-origin paths", () => {
    expect(resolveContinue("https://app.onolys.com/verify-email?x=1", o)).toEqual({ kind: "path", path: "/verify-email?x=1" });
    expect(resolveContinue("/settings", o)).toEqual({ kind: "path", path: "/settings" });
  });
  it("allows known app hosts (staging shares the project) as external", () => {
    expect(resolveContinue("https://onolys-app-staging.web.app/verify-email", o)).toEqual({
      kind: "external",
      href: "https://onolys-app-staging.web.app/verify-email",
    });
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
    renderApp(`/auth/action?mode=resetPassword&oobCode=${code}`, { service });
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
    await h1("Password updated");
    expect(service.calls.passwordResets).toBe(1);
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    await service.signIn("a@clinic.org", "longenough1");
  });

  it("shows an expired message for a bad code", async () => {
    renderApp("/auth/action?mode=resetPassword&oobCode=bad");
    await h1("Reset link expired");
    expect(screen.getByRole("link", { name: "Request a new reset link" })).toHaveAttribute("href", "/forgot-password");
  });
});

describe("/auth/action other", () => {
  it.each(["/auth/action", "/auth/action?mode=other&oobCode=x", "/auth/action?mode=verifyEmail", "/auth/action?mode=resetPassword"])(
    "%s is not valid",
    async (path) => {
      renderApp(path);
      await h1("This link isn't valid");
    },
  );
});
