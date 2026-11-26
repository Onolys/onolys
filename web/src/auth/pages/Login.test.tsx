import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it } from "vitest";
import { AuthProvider } from "../AuthProvider";
import { createFakeAuthService } from "../fakeService";
import { Login } from "./Login";

afterEach(cleanup);
const show = (props: { showGoogle?: boolean }) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider service={createFakeAuthService()}>
        <MemoryRouter>
          <Login {...props} />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );

it("shows Continue with Google by default", () => {
  show({});
  expect(screen.getByRole("button", { name: "Continue with Google" })).toBeTruthy();
});

it("hides Continue with Google with showGoogle={false}", () => {
  show({ showGoogle: false });
  expect(screen.getByRole("button", { name: "Log in" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Continue with Google" })).toBeNull();
});
