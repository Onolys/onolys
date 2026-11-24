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

describe("unknown server status (C17)", () => {
  it("falls back to a neutral chip and does not poll", async () => {
    const { chipFor } = await import("./chips");
    expect(chipFor("brand_new_state" as never)).toEqual({ text: "Status unavailable", tone: "neutral" });
    expect(chipFor("failed")).toBe(STATUS_CHIP.failed);
    expect(sessionsRefetchInterval([{ status: "brand_new_state" as never }])).toBe(false);
  });
});
