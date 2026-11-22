import { describe, expect, it } from "vitest";
import { ApiError } from "./api/errors";
import { makeQueryClient } from "./queryClient";

describe("makeQueryClient", () => {
  it("keeps cached data only briefly, in memory (R8: no PHI persisted)", () => {
    const opts = makeQueryClient().getDefaultOptions().queries;
    expect(opts?.gcTime).toBeLessThanOrEqual(5 * 60 * 1000);
    expect(opts?.gcTime).toBeGreaterThan(0);
  });

  it("retries once, but never a 4xx ApiError (W24)", () => {
    const retry = makeQueryClient().getDefaultOptions().queries?.retry as (n: number, e: Error) => boolean;
    expect(retry(0, new ApiError(404, "not_found", []))).toBe(false);
    expect(retry(0, new ApiError(429, "rate_limited", []))).toBe(false);
    expect(retry(0, new ApiError(503, "upstream_unavailable", []))).toBe(true);
    expect(retry(0, new TypeError("network"))).toBe(true);
    expect(retry(1, new ApiError(503, "upstream_unavailable", []))).toBe(false);
  });
});
