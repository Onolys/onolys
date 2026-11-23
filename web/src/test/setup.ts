import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
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

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  setStatusListener(mockEmitter); // the in-memory status doc stands in for Firestore
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  mockBackend.reset();
});
afterAll(() => server.close());
