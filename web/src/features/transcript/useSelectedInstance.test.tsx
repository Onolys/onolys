import { act, renderHook } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { MemoryRouter, useNavigate } from "react-router";
import { describe, expect, it } from "vitest";
import { parseInstanceHash, useSelectedInstance } from "./useSelectedInstance";

const wrap = (initial: string) => ({ children }: { children: ReactNode }) =>
  createElement(MemoryRouter, { initialEntries: [initial] }, children);

describe("instance hash", () => {
  it("parses #i=<id> and ignores anything else", () => {
    expect(parseInstanceHash("#i=abc_1")).toBe("abc_1");
    expect(parseInstanceHash("#i=")).toBeNull();
    expect(parseInstanceHash("#other")).toBeNull();
    expect(parseInstanceHash("")).toBeNull();
    expect(parseInstanceHash("#i=%3Cb%3E")).toBe("<b>");
  });

  it("reads the router hash, selects through the router, and follows SPA navigation (W27)", () => {
    const { result } = renderHook(() => ({ sel: useSelectedInstance(), nav: useNavigate() }), { wrapper: wrap("/r#i=first") });
    expect(result.current.sel[0]).toBe("first");
    act(() => result.current.sel[1]("second"));
    expect(result.current.sel[0]).toBe("second");
    act(() => void result.current.nav("/elsewhere"));
    expect(result.current.sel[0]).toBeNull();
    act(() => void result.current.nav("/r#i=third"));
    expect(result.current.sel[0]).toBe("third");
    act(() => result.current.sel[1](null));
    expect(result.current.sel[0]).toBeNull();
  });
});
