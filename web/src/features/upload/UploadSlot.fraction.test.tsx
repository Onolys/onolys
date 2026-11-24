import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionStatusDoc } from "../../api/statusListener";
import { UploadSlot } from "./UploadSlot";
import * as uploader from "./uploader";

vi.mock("../../auth/useApiClient", () => ({ useApiClient: () => ({}) }));
// The no-job branch now renders the resume form (react-query hooks); this test only reads the fraction.
vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useQuery: () => ({ data: undefined }),
}));

const doc = { state: "uploading" } as SessionStatusDoc;
afterEach(() => vi.restoreAllMocks());

describe("UploadSlot onFraction", () => {
  it("reports the byte fraction from the job, null with no job", () => {
    const onFraction = vi.fn();
    vi.spyOn(uploader, "subscribeRegistry").mockImplementation(() => () => undefined);
    const getJob = vi.spyOn(uploader, "getJob").mockReturnValue(undefined);
    const { rerender } = render(<UploadSlot sessionId="s1" doc={doc} onFraction={onFraction} />);
    expect(onFraction).toHaveBeenLastCalledWith(null);

    const state = { phase: "uploading", loaded: 25, total: 100, attempt: 0 };
    const job = {
      subscribe: () => () => undefined,
      getState: () => state,
      cancel: vi.fn(),
      retry: vi.fn(),
    };
    getJob.mockReturnValue(job as unknown as uploader.UploadJob);
    rerender(<UploadSlot sessionId="s1" doc={{ ...doc }} onFraction={onFraction} />);
    expect(onFraction).toHaveBeenLastCalledWith(0.25);
  });
});
