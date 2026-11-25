import { describe, expect, it } from "vitest";
import { ApiError } from "./api/errors";
import { pageLoadError } from "./pageLoadError";

describe("essential page query failures", () => {
  it("escalates initial network/server errors and preserves API error statuses", () => {
    const empty = { state: { data: undefined } };
    expect(pageLoadError(new TypeError("Failed to fetch"), empty)).toBe(true);
    for (const status of [500, 502, 503, 504]) {
      const error = new ApiError(status, "internal_error", []);
      expect(pageLoadError(error, empty)).toBe(true);
      expect(error.status).toBe(status);
    }
  });
  it("keeps validation, auth, not found, limits and background failures local", () => {
    for (const status of [400, 401, 403, 404, 409, 422, 429]) {
      expect(pageLoadError(new ApiError(status, "unknown", []), { state: { data: undefined } })).toBe(false);
    }
    expect(pageLoadError(new ApiError(503, "internal_error", []), { state: { data: { items: [] } } })).toBe(false);
    expect(pageLoadError(new TypeError("Failed to fetch"), { state: { data: [] } })).toBe(false);
  });
});
