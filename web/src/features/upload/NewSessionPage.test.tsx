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
const goal = (t = "Walk more in the evenings") => userEvent.type(screen.getByLabelText(/change goal/i), t);

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
    await goal();
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
    await goal();
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
    await goal();
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
    await goal();
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

describe("New session form: change goal + one submit (flag off)", () => {
  type Call = { m: string; path: string; body?: unknown };
  let calls: Call[];
  const record = (m: string, path: string, body?: unknown) => calls.push({ m, path, body });
  // Late requests of an earlier test's session (same mock ids) can land first; count from this test's create.
  const mine = () => {
    const i = calls.findIndex((c) => c.m === "POST" && c.path === "/v1/sessions");
    return i < 0 ? [] : calls.slice(i);
  };
  const rating = () => mine().filter((c) => c.m === "PUT" && c.path.endsWith("/rating"));
  const audio = () => mine().filter((c) => c.m === "POST" && c.path.endsWith("/audio"));
  const start = () => screen.getByRole("button", { name: /start/i });

  beforeEach(() => {
    calls = [];
    server.events.on("request:start", async ({ request }) => {
      const p = new URL(request.url).pathname;
      if (!p.startsWith("/v1/sessions")) return;
      const text = request.method === "GET" ? "" : await request.clone().text();
      record(request.method, p, text ? JSON.parse(text) : undefined);
    });
  });
  afterEach(() => server.events.removeAllListeners());

  it("has a required Change goal and no time-range or setup-screen fields", async () => {
    await open();
    expect(screen.getByLabelText(/change goal/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/from|to \(|time range|coded/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /save setup/i })).toBeNull();
    expect(screen.getAllByRole("button", { name: /start|save/i })).toHaveLength(1);
  });

  it("the goal is a textarea with a soft length counter", async () => {
    await open();
    const field = screen.getByLabelText(/change goal/i);
    expect(field.tagName).toBe("TEXTAREA");
    expect(screen.getByText("0 / 1,000")).toBeInTheDocument();
    await goal("abc");
    expect(screen.getByText("3 / 1,000")).toBeInTheDocument();
  });

  it("blocks Start while the goal is blank or whitespace, and makes no request", async () => {
    await open();
    await choose(mp3());
    expect(start()).toBeDisabled();
    await goal("   ");
    expect(start()).toBeDisabled();
    expect(calls.filter((c) => c.m === "POST")).toHaveLength(0);
    await userEvent.type(screen.getByLabelText(/change goal/i), "x");
    expect(start()).toBeEnabled();
  });

  it("one click: create session, PUT /rating (final, no_rating, goal only), then audio registration", async () => {
    const { router } = await open();
    await choose(mp3());
    await goal("Walk more");
    await userEvent.click(start());
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    const order = mine().map((c) => `${c.m} ${c.path.replace(/\/sessions\/[^/]+/, "/sessions/:id")}`);
    expect(order.indexOf("POST /v1/sessions")).toBeLessThan(order.indexOf("PUT /v1/sessions/:id/rating"));
    expect(order.indexOf("PUT /v1/sessions/:id/rating")).toBeLessThan(order.indexOf("POST /v1/sessions/:id/audio"));
    expect(rating()).toHaveLength(1);
    expect(rating()[0]!.body).toEqual({ final: true, no_rating: true, card: { change_goal: "Walk more" } });
    expect(JSON.stringify(rating()[0]!.body)).not.toContain("coded_span");
  });

  it("422 rating_invalid shows a field message and registers no audio", async () => {
    server.use(
      http.put("*/v1/sessions/:id/rating", () =>
        HttpResponse.json(
          { status: 422, message: "x", request_id: "r", details: [{ code: "rating_invalid", message: "x", field: "change_goal", issue: "too_long" }] },
          { status: 422 },
        ),
      ),
    );
    const { router } = await open();
    await choose(mp3());
    await goal("Walk more");
    await userEvent.click(start());
    expect(await screen.findByText(/too long/i)).toBeInTheDocument();
    expect(audio()).toHaveLength(0);
    expect(here(router)).toBe("/sessions/new");
  });

  it("409 rating_final on the PUT counts as success and audio goes on", async () => {
    server.use(
      http.put("*/v1/sessions/:id/rating", () =>
        HttpResponse.json({ status: 409, message: "x", request_id: "r", details: [{ code: "rating_final", message: "x" }] }, { status: 409 }),
      ),
    );
    const { router } = await open();
    await choose(mp3());
    await goal();
    await userEvent.click(start());
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    expect(audio().length).toBeGreaterThanOrEqual(1); // the app-level uploader may ask again
  });

  it("an audio failure after a good PUT retries without a second PUT", async () => {
    let fail = true;
    server.use(
      http.post("*/v1/sessions/:id/audio", () =>
        fail
          ? HttpResponse.json({ status: 500, message: "x", request_id: "r", details: [{ code: "internal_error", message: "x" }] }, { status: 500 })
          : HttpResponse.json({ upload_url: "https://uploads.mock.invalid/x", upload_id: "u1", required_headers: {} }),
      ),
    );
    const { router } = await open();
    await choose(mp3());
    await goal();
    await userEvent.click(start());
    await waitFor(() => expect(audio()).toHaveLength(1));
    await waitFor(() => expect(start()).toBeEnabled());
    expect(screen.getByLabelText(/change goal/i)).toBeDisabled(); // saved: an edit would be silently dropped
    fail = false;
    await userEvent.click(start());
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    expect(audio().length).toBeGreaterThan(1);
    expect(rating()).toHaveLength(1);
    expect(mine().filter((c) => c.m === "POST" && c.path === "/v1/sessions")).toHaveLength(1);
  });
});

describe("New session form: flag on", () => {
  beforeEach(() => vi.stubEnv("VITE_RATING_ENABLED", "true"));
  afterEach(() => vi.unstubAllEnvs());

  it("shows no setup fields and Start needs only the audio; no rating PUT", async () => {
    const puts: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "PUT") puts.push(request.url);
    });
    const { router } = await open();
    expect(screen.queryByLabelText(/change goal/i)).toBeNull();
    await choose(mp3());
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    expect(puts.filter((u) => u.endsWith("/rating"))).toHaveLength(0);
    server.events.removeAllListeners();
  });
});
