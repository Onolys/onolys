import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionStatusDoc } from "../../api/statusListener";
import { UploadSlot } from "./UploadSlot";
import * as uploader from "./uploader";

vi.mock("../../auth/useApiClient", () => ({ useApiClient: () => ({}) }));
vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useQuery: () => ({ data: undefined }),
}));

afterEach(() => vi.restoreAllMocks());
const docIn = (state: string) => ({ state }) as SessionStatusDoc;

describe("UploadSlot resume (C4)", () => {
  it.each(["created", "uploading", "upload_incomplete"])("%s with no job in this tab offers Resume", (state) => {
    vi.spyOn(uploader, "subscribeRegistry").mockImplementation(() => () => undefined);
    vi.spyOn(uploader, "getJob").mockReturnValue(undefined);
    render(<UploadSlot sessionId="s1" doc={docIn(state)} />);
    expect(screen.getByRole("button", { name: "Resume upload" })).toBeInTheDocument();
    expect(screen.queryByText(/start a new session/i)).toBeNull();
  });

  it("a running job shows progress, not Resume", () => {
    vi.spyOn(uploader, "subscribeRegistry").mockImplementation(() => () => undefined);
    const running = { phase: "uploading", loaded: 1, total: 4, attempt: 0 };
    const job = {
      subscribe: () => () => undefined,
      getState: () => running,
      cancel: vi.fn(),
      retry: vi.fn(),
    };
    vi.spyOn(uploader, "getJob").mockReturnValue(job as unknown as uploader.UploadJob);
    render(<UploadSlot sessionId="s1" doc={docIn("uploading")} />);
    expect(screen.queryByRole("button", { name: "Resume upload" })).toBeNull();
    expect(screen.getByLabelText("Upload progress")).toBeInTheDocument();
  });

  it("C12: a failed job shows the carried error message", () => {
    vi.spyOn(uploader, "subscribeRegistry").mockImplementation(() => () => undefined);
    const state = {
      phase: "failed",
      loaded: 4,
      total: 4,
      attempt: 0,
      error: { code: "invalid_state", message: "That isn't possible at this stage of the session. Refresh and try again." },
    };
    const job = { subscribe: () => () => undefined, getState: () => state, cancel: vi.fn(), retry: vi.fn() };
    vi.spyOn(uploader, "getJob").mockReturnValue(job as unknown as uploader.UploadJob);
    render(<UploadSlot sessionId="s1" doc={docIn("uploading")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Refresh and try again");
  });
});
