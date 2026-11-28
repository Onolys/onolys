import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { EMULATOR_URL } from "@onolys/common/auth/testing";
import { HttpNetworkFrame } from "msw/experimental";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { setStatusListener } from "../api/statusListener";
import { mockBackend, mockEmitter, server } from "../mocks/server";

// jsdom lacks the modal <dialog> API and scrollIntoView: minimal stand-ins.
if (
  typeof HTMLDialogElement !== "undefined" &&
  !HTMLDialogElement.prototype.showModal
) {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
if (!Element.prototype.scrollIntoView)
  Element.prototype.scrollIntoView = vi.fn();

// Radix (via @onolys/common) needs these jsdom lacks: ResizeObserver, matchMedia, pointer capture, DOMRect.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false;
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => {};
if (typeof globalThis.DOMRect === "undefined") {
  globalThis.DOMRect = class DOMRect {
    constructor(
      public x = 0,
      public y = 0,
      public width = 0,
      public height = 0,
    ) {}
    get top() { return this.y; }
    get left() { return this.x; }
    get right() { return this.x + this.width; }
    get bottom() { return this.y + this.height; }
    toJSON() { return { x: this.x, y: this.y, width: this.width, height: this.height }; }
  } as unknown as typeof DOMRect;
}

beforeAll(() => {
  // Any request without a handler fails the test, except the Firebase Auth emulator (real sign-in, not an API fake).
  server.listen({
    onUnhandledFrame({ frame, defaults }) {
      if (frame instanceof HttpNetworkFrame && new URL(frame.data.request.url).origin === EMULATOR_URL) return;
      defaults.error();
    },
  });
  setStatusListener(mockEmitter); // the in-memory status doc stands in for Firestore
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  mockBackend.reset();
});
afterAll(() => server.close());
