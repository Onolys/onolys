import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockBackend, server } from "../../mocks/server";
import { here, renderApp } from "../../test/renderApp";
import { MAX_AUDIO_BYTES } from "./precheck";
import { getJob } from "./uploader";

const USER = { email: "rater@clinic.org", verified: true };
const mp3 = () => new File([new Uint8Array(100)], "visit.mp3", { type: "audio/mpeg" });

let seconds = 15 * 60;
beforeEach(() => {
  seconds = 15 * 60;
  // jsdom never loads media metadata; a stand-in that reports `seconds`.
  vi.stubGlobal(
    "Audio",
    class {
      duration = seconds;
      onloadedmetadata: (() => void) | null = null;
      onerror: (() => void) | null = null;
      preload = "";
      set src(_: string) {
        queueMicrotask(() => this.onloadedmetadata?.());
      }
      removeAttribute() {}
    },
  );
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }));
});
afterEach(() => vi.unstubAllGlobals());

async function open(path = "/sessions/new") {
  const r = renderApp(path, { user: USER });
  await screen.findByRole("heading", { level: 1, name: "New session" });
  return r;
}
const choose = (f: File) => userEvent.upload(screen.getByLabelText(/audio recording/i), f);

describe("New session form", () => {
  it("has audio, language (auto default, 3 options), optional title and no Advanced section", async () => {
    await open();
    const lang = screen.getByLabelText("Language") as HTMLSelectElement;
    expect(lang.value).toBe("auto");
    expect(Array.from(lang.options).map((o) => o.value)).toEqual(["auto", "en-US", "en-GB"]);
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.queryByText(/advanced/i)).toBeNull();
    expect(screen.getByRole("button", { name: /start/i })).toBeDisabled();
  });

  it("blocks an oversized file with the export message", async () => {
    await open();
    const big = new File([new Uint8Array(1)], "big.wav", { type: "audio/wav" });
    Object.defineProperty(big, "size", { value: MAX_AUDIO_BYTES + 1 });
    await choose(big);
    expect(await screen.findByRole("alert")).toHaveTextContent("Export it as m4a or mp3");
    expect(screen.getByRole("button", { name: /start/i })).toBeDisabled();
  });

  it("blocks a recording over 20 minutes and warns under 10 from the audio metadata", async () => {
    await open();
    seconds = 26 * 60;
    await choose(mp3());
    expect(await screen.findByRole("alert")).toHaveTextContent("longer than 20 minutes");
    expect(screen.getByRole("button", { name: /start/i })).toBeDisabled();
    seconds = 5 * 60;
    await choose(new File([new Uint8Array(100)], "short.mp3", { type: "audio/mpeg" }));
    expect(await screen.findByRole("status")).toHaveTextContent("under 10 minutes");
    expect(screen.getByRole("button", { name: /start/i })).toBeEnabled();
  });

  it("creates the session, requests the audio URL, registers the upload and navigates at once", async () => {
    const { router } = await open();
    await userEvent.type(screen.getByLabelText(/title/i), "Visit 3");
    await userEvent.selectOptions(screen.getByLabelText("Language"), "en-GB");
    await choose(mp3());
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    const id = here(router).split("/")[2]!;
    expect(getJob(id)).toBeDefined();
    expect(mockBackend.getSession("u_rater_clinic_org", id).status).toBe("uploading");
  });

  it("W17: the latest pick wins when an earlier file's check finishes last; Start waits with 'Checking file…'", async () => {
    // jsdom has no media metadata: hold the first file's read, answer the second at once
    let release: () => void = () => {};
    vi.stubGlobal(
      "Audio",
      class {
        onloadedmetadata: (() => void) | null = null;
        onerror: (() => void) | null = null;
        duration = 0;
        preload = "";
        set src(url: string) {
          const slow = url === "blob:slow";
          this.duration = slow ? 60 : 15 * 60;
          if (slow) release = () => this.onloadedmetadata?.();
          else queueMicrotask(() => this.onloadedmetadata?.());
        }
        removeAttribute() {}
      },
    );
    vi.stubGlobal(
      "URL",
      Object.assign(URL, {
        createObjectURL: (f: File) => `blob:${f.name === "slow.mp3" ? "slow" : "fast"}`,
        revokeObjectURL: () => {},
      }),
    );
    await open();
    const start = screen.getByRole("button", { name: /start/i });
    await choose(new File([new Uint8Array(10)], "slow.mp3", { type: "audio/mpeg" }));
    expect(await screen.findByText("Checking file…")).toBeInTheDocument();
    expect(start).toBeDisabled();
    await choose(new File([new Uint8Array(10)], "fast.mp3", { type: "audio/mpeg" }));
    await waitFor(() => expect(start).toBeEnabled());
    act(() => release()); // the old file's answer arrives late
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("status")).toBeNull(); // not slow.mp3's "under 10 minutes"
    expect(screen.queryByText("Checking file…")).toBeNull();
    expect(start).toBeEnabled();
  });

  it("W30: a session prepared after the user left the form does not pull them back", async () => {
    let open_gate: () => void = () => {};
    const gate = new Promise<void>((r) => (open_gate = r));
    server.use(
      http.post("*/v1/sessions/:id/audio", async () => {
        await gate;
        return HttpResponse.json({ upload_url: "https://uploads.mock.invalid/x", upload_id: "u1", required_headers: {} });
      }),
    );
    const { router } = await open();
    await choose(mp3());
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    await act(() => router.navigate("/settings"));
    open_gate();
    await new Promise((r) => setTimeout(r, 50));
    expect(here(router)).toBe("/settings");
  });

  it("prefills the title from ?from=<id>", async () => {
    const id = mockBackend.createSession("u_rater_clinic_org", { title: "Old visit" }).session.id;
    await open(`/sessions/new?from=${id}`);
    await waitFor(() => expect(screen.getByLabelText(/title/i)).toHaveValue("Old visit"));
  });
});
