import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { RouteTitle, titleForPath } from "./routeTitle";

afterEach(() => {
  document.title = "Onolys";
});

describe("route titles (C16)", () => {
  it.each([
    ["/new", "New session · Onolys"],
    ["/sessions", "Sessions · Onolys"],
    ["/sessions/new", "Upload a session · Onolys"],
    ["/sessions/abc123", "Session · Onolys"],
    ["/sessions/abc123/reports/2", "Report · Onolys"],
    ["/interviews/new", "New interview · Onolys"],
    ["/interviews/xyz", "Interview · Onolys"],
    ["/settings", "Settings · Onolys"],
    ["/login", "Log in · Onolys"],
    ["/signup", "Sign up · Onolys"],
    ["/privacy", "Privacy policy · Onolys"],
    ["/terms", "Terms of service · Onolys"],
    ["/sample", "Sample report · Onolys"],
    ["/nope/nothing", "Page not found · Onolys"],
    ["/", "Onolys"],
  ])("%s -> %s", (path, title) => {
    expect(titleForPath(path)).toBe(title);
  });

  it("never puts an id from the URL in the title", () => {
    expect(titleForPath("/sessions/secret-id-1")).not.toContain("secret");
  });

  it("RouteTitle sets document.title for the current location", () => {
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <RouteTitle />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Settings · Onolys");
  });
});
