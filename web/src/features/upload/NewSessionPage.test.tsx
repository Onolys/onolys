import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockBackend, server } from "../../mocks/server";
import { here, renderApp } from "../../test/renderApp";
import { UPLOAD_LIMITS } from "../../mocks/handlers";
import { clearJobs, getJob } from "./uploader";

const USER = { email: "rater@clinic.org", verified: true };
const mp3 = () => new File([new Uint8Array(100)], "visit.mp3", { type: "audio/mpeg" });

let seconds = 15 * 60;
beforeEach(() => {
  clearJobs();
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
afterEach(() => { clearJobs(); vi.unstubAllGlobals(); });

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
    Object.defineProperty(big, "size", { value: UPLOAD_LIMITS.max_bytes + 1 });
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
    // the same-origin mock PUT may already have completed (validating); either way the upload was registered
    expect(mockBackend.getSession("u_rater_clinic_org", id).status).toMatch(/^(uploading|validating)$/);
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

describe("Transcript upload", () => {
  async function transcript(file = new File(["Alex: Hello\nSam: Hi"], "visit.txt")) {
    await userEvent.click(screen.getByRole("radio", { name: "Transcript" }));
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText("Transcript file"), file);
  }
  it("offers audio or transcript and clears picks when changing source", async () => {
    await open();
    expect(screen.getByRole("radio", { name: "Audio" })).toBeChecked();
    await transcript();
    expect(screen.getByLabelText("Transcript file")).toHaveAttribute("accept", ".json,.txt");
    await goal();
    expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
    await userEvent.click(screen.getByRole("radio", { name: "Audio" }));
    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  });
  it.each([['visit.pdf', 10, /json or txt/i], ['visit.txt', 1024 * 1024 + 1, /over 1 MB/i]])("blocks %s before submission", async (name, size, message) => {
    await open();
    const f = new File(["x"], name);
    Object.defineProperty(f, "size", { value: size });
    await transcript(f);
    await goal();
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  });
  it.each([['visit.txt', 'text/plain', 'Alex: Hello\nSam: Hi'], ['visit.json', 'application/json', '{"turns":[]}']])("PUTs raw %s with auth and no audio steps", async (name, contentType, content) => {
    const audio = vi.fn();
    const received: unknown[] = [];
    server.use(http.put("*/v1/sessions/:id/transcript", async ({ request, params }) => {
      received.push({ content: await request.text(), type: request.headers.get("content-type"), auth: request.headers.get("authorization") });
      return HttpResponse.json({ session: { id: params.id, status: "awaiting_input" } }, { status: 202 });
    }), http.post("*/v1/sessions/:id/audio", () => { audio(); return HttpResponse.json({}); }));
    const { router } = await open();
    await transcript(new File([content], name, { type: "application/octet-stream" }));
    await goal();
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    expect(received).toEqual([{ content, type: contentType, auth: "Bearer test:u_rater_clinic_org" }]);
    expect(audio).not.toHaveBeenCalled();
  });
  it.each([
    ['transcript_invalid', /couldn't read this transcript/i], ['transcript_too_large', /over 1 MB/i],
    ['empty_transcript', /at least 50 words/i], ['session_too_long', /narrower coded_span/i],
  ])("shows the shared error card for %s", async (code, message) => {
    server.use(http.put("*/v1/sessions/:id/transcript", () => HttpResponse.json({ status: 422, details: [{ code, message: 'private text' }], request_id: 'transcript_ref' }, { status: 422 })));
    await open();
    await transcript();
    await goal();
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("alert")).toHaveTextContent("transcript_ref");
    expect(screen.getByRole("alert")).not.toHaveTextContent("private text");
  });
});

describe("Transcript upload with the mock API", () => {
  it.each([['Alex', 'Sam', true], ['T', 'C', false]])("%s/%s labels use the speaker gate appropriately", async (a, b, gate) => {
    const content = `${a}: ${'A synthetic example about walking outside. '.repeat(5)}\n${b}: ${'Another synthetic example about walking outside. '.repeat(5)}`;
    await open();
    await userEvent.click(screen.getByRole('radio', { name: 'Transcript' }));
    await userEvent.upload(screen.getByLabelText('Transcript file'), new File([content], 'walk.txt', { type: 'text/plain' }));
    await goal();
    await userEvent.click(screen.getByRole('button', { name: 'Start' }));
    await screen.findByRole('list', { name: 'Progress' });
    if (gate) expect(await screen.findByRole('heading', { name: 'Speaker Alex' })).toBeInTheDocument();
    else {
      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Coding the session'));
      expect(screen.queryByRole('heading', { name: 'Who is the clinician?' })).toBeNull();
    }
  });
});

describe("New session form: prepare failures (M-8, C10, C19)", () => {
  const V1 = "/v1/sessions";
  let calls: { m: string; path: string; body?: unknown }[];
  beforeEach(() => {
    calls = [];
    server.events.on("request:start", async ({ request }) => {
      const p = new URL(request.url).pathname;
      if (!p.startsWith(V1)) return;
      const text = request.method === "GET" ? "" : await request.clone().text();
      let body: unknown;
      try {
        body = text ? JSON.parse(text) : undefined;
      } catch {
        body = text;
      }
      calls.push({ m: request.method, path: p, body });
    });
  });
  afterEach(() => server.events.removeAllListeners());
  const creates = () => calls.filter((c) => c.m === "POST" && c.path === V1);
  const deletes = () => calls.filter((c) => c.m === "DELETE");
  const err422 = (code: string) =>
    HttpResponse.json({ status: 422, details: [{ code, message: "x" }], request_id: "r" }, { status: 422 });
  const pickTranscript = async (file: File) => {
    await userEvent.click(screen.getByRole("radio", { name: "Transcript" }));
    await userEvent.setup({ applyAccept: false }).upload(screen.getByLabelText("Transcript file"), file);
    await goal();
  };
  const startBtn = () => screen.getByRole("button", { name: "Start" });

  it("M-8: a transcript that is not valid JSON is rejected before any session is created", async () => {
    await open();
    await pickTranscript(new File(["{not json"], "visit.json"));
    await userEvent.click(startBtn());
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't read this transcript/i);
    expect(creates()).toHaveLength(0);
  });

  it("M-8: an empty transcript is rejected before any session is created", async () => {
    await open();
    await pickTranscript(new File(["   \n"], "visit.txt"));
    await userEvent.click(startBtn());
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 50 words/i);
    expect(creates()).toHaveLength(0);
  });

  it("M-8: a terminal transcript error deletes the just-created session, and a resubmit starts clean", async () => {
    let reject = true;
    server.use(
      http.put("*/v1/sessions/:id/transcript", ({ params }) =>
        reject ? err422("transcript_invalid") : HttpResponse.json({ session: { id: params.id, status: "awaiting_input" } }, { status: 202 }),
      ),
    );
    const { router } = await open();
    await pickTranscript(new File(["Alex: Hello\nSam: Hi"], "visit.txt"));
    await userEvent.click(startBtn());
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't read this transcript/i);
    await waitFor(() => expect(deletes()).toHaveLength(1));
    const orphan = creates().length === 1 ? deletes()[0]!.path.split("/")[3] : "";
    expect(orphan).toBeTruthy();
    expect(startBtn()).toBeEnabled();
    expect(screen.getByLabelText(/change goal/i)).toBeEnabled(); // nothing is locked to the deleted session
    reject = false;
    await userEvent.type(screen.getByLabelText(/title/i), "Fixed");
    await userEvent.click(startBtn());
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    expect(creates()).toHaveLength(2);
    expect(here(router)).not.toContain(orphan!);
  });

  it("M-8: resubmitting the same body after cleanup creates a fresh session (new idempotency key)", async () => {
    server.use(http.put("*/v1/sessions/:id/transcript", () => err422("transcript_invalid")));
    const keys: string[] = [];
    server.events.on("request:start", ({ request }) => {
      const k = request.headers.get("idempotency-key");
      if (k && request.method === "POST") keys.push(k);
    });
    await open();
    await pickTranscript(new File(["Alex: Hello\nSam: Hi"], "visit.txt"));
    await userEvent.click(startBtn());
    await waitFor(() => expect(deletes()).toHaveLength(1));
    await waitFor(() => expect(startBtn()).toBeEnabled());
    await userEvent.click(startBtn());
    await waitFor(() => expect(deletes()).toHaveLength(2));
    expect(keys).toHaveLength(2);
    expect(new Set(keys).size).toBe(2);
  });

  it("M-8: a terminal audio prepare error (422) deletes the new session", async () => {
    server.use(http.post("*/v1/sessions/:id/audio", () => err422("unsupported_audio")));
    await open();
    await choose(mp3());
    await goal();
    await userEvent.click(startBtn());
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't use this file type/i);
    await waitFor(() => expect(deletes()).toHaveLength(1));
  });

  it("C10: the chosen language is sent with the session create on the transcript path", async () => {
    server.use(http.put("*/v1/sessions/:id/transcript", ({ params }) => HttpResponse.json({ session: { id: params.id, status: "awaiting_input" } }, { status: 202 })));
    const { router } = await open();
    await userEvent.selectOptions(screen.getByLabelText("Language"), "en-GB");
    await pickTranscript(new File(["Alex: Hello\nSam: Hi"], "visit.txt"));
    await userEvent.click(startBtn());
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new$)[^/]+$/));
    expect(creates()[0]!.body).toMatchObject({ language: "en-GB" });
  });

  it("C19: the audio note is derived from the served upload limits", async () => {
    server.use(
      http.get("*/v1/upload-limits", () =>
        HttpResponse.json({ ...UPLOAD_LIMITS, max_bytes: 100 * 1024 * 1024, max_duration_s: 30 * 60, short_warning_s: 8 * 60 }),
      ),
    );
    await open();
    expect(await screen.findByText(/up to 100 MB, 8 to 30 minutes/)).toBeInTheDocument();
    expect(screen.queryByText(/300 MB/)).toBeNull();
  });
});
