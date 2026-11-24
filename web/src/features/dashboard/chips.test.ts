import { describe, expect, it } from "vitest";
import { STATUS_CHIP, sessionsRefetchInterval } from "./chips";

describe("STATUS_CHIP", () => {
  it("cancelled reads Cancelled in the muted tone", () => {
    expect(STATUS_CHIP.cancelled).toEqual({ text: "Cancelled", tone: "muted" });
  });
  it("a cancelled session does not keep the list polling", () => {
    expect(sessionsRefetchInterval([{ status: "cancelled" }])).toBe(false);
  });
});
