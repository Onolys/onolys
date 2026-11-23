/**
 * SP10 Task 11: landing cards, picker, live page, End -> upload -> session, warn toast, reconnect, discard (AC9).
 * MSW serves /v1, the fake relay plays the socket, the audio engine is a stub (no browser audio in jsdom).
 */
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockBackend, server } from "../../mocks/server";
import { here, renderApp } from "../../test/renderApp";
import { configureFakeRelay, lastFakeRelay, resetFakeRelay } from "./relay/fakeRelay";

const engines: FakeEngine[] = [];
class FakeEngine {
  started = false;
  closed = false;
  played = 0;
  flushed = 0;
  stopped = 0;
  paused = 0;
  resumed = 0;
  mimeType = "audio/webm";
  onCaptureFrame: (f: ArrayBuffer) => void;
  constructor(o: { onCaptureFrame: (f: ArrayBuffer) => void }) {
    this.onCaptureFrame = o.onCaptureFrame;
    engines.push(this);
  }
  async start() {
    if (slowMic) await new Promise((r) => setTimeout(r, 50));
    if (denyMic) throw new Error("denied");
    this.started = true;
  }
  playPcm24k() {
    this.played++;
  }
  flush() {
    this.flushed++;
  }
  pauseRecording() {
    this.paused++;
  }
  resumeRecording() {
    this.resumed++;
  }
  async stopRecording() {
    this.stopped++;
    return new Blob(["abc"], { type: "audio/webm;codecs=opus" });
  }
  close() {
    this.closed = true;
  }
}
let denyMic = false;
let slowMic = false;
vi.mock("./audio/engine", () => ({ createAudioEngine: (o: { onCaptureFrame: (f: ArrayBuffer) => void }) => new FakeEngine(o) }));

class FetchXhr {
  status = 0;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  upload = { onprogress: null as unknown };
  private method = "";
  private url = "";
  private headers: Record<string, string> = {};
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  send(body: Blob) {
    void fetch(this.url, { method: this.method, headers: this.headers, body }).then(
      (r) => {
        this.status = r.status;
        this.onload?.();
      },
      () => this.onerror?.(),
    );
  }
  abort() {}
}

const UID = "u_rater_clinic_org";
const USER = { email: "rater@clinic.org", verified: true };
const main = () => within(screen.getByRole("main"));

beforeEach(() => {
  denyMic = false;
  slowMic = false;
  engines.length = 0;
  vi.stubEnv("VITE_USE_MOCKS", "true"); // createRelaySocket -> the fake relay
  vi.stubGlobal("XMLHttpRequest", FetchXhr);
  configureFakeRelay({ autoTick: false });
});
afterEach(() => {
  resetFakeRelay();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

/** Picker -> live page, started and connected (relay `ready` received). */
async function startLive(u: ReturnType<typeof userEvent.setup>, router: Parameters<typeof here>[0]) {
  await u.click(await main().findByRole("radio", { name: /Reluctant patient/ }));
  await u.click(main().getByRole("button", { name: "Start interview" }));
  await waitFor(() => expect(here(router)).toMatch(/^\/interviews\/iv_/));
  await u.click(await main().findByRole("button", { name: "Start talking" }));
  await waitFor(() => expect(lastFakeRelay()?.readyState).toBe(1));
  await waitFor(() => expect(main().getByText("Listening")).toBeInTheDocument());
  return here(router).split("/")[2]!;
}

describe("landing cards", () => {
  it("shows both cards with usage, the interview card linking to the picker", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/", { user: USER });
    const interviewCard = within(await main().findByRole("region", { name: /Practise with an AI client/ }));
    expect(await interviewCard.findByRole("button", { name: "5 of 5 left today" })).toHaveTextContent("5/5");
    expect(interviewCard.queryByText(/this month/)).toBeNull();
    const rate = within(main().getByRole("region", { name: "Rate a recording" }));
    expect(rate.getByRole("button", { name: "20 of 20 left today" })).toHaveTextContent("20/20");
    expect(rate.getByRole("link", { name: "New session" })).toHaveAttribute("href", "/sessions/new");
    await u.click(interviewCard.getByRole("link", { name: "Start AI Interview" }));
    expect(here(router)).toBe("/interviews/new");
  });

  it.each([
    ["day", { interview: { day: 0 } }, /today's AI interview limit\. It resets at/],
  ])("disables Start AI Interview at the %s cap with the period message", async (_n, caps, text) => {
    mockBackend.configure({ caps });
    renderApp("/", { user: USER });
    const btn = await main().findByRole("button", { name: "Start AI Interview" });
    expect(btn).toBeDisabled();
    expect(main().queryByRole("link", { name: "Start AI Interview" })).toBeNull();
    expect(main().getByText(text)).toBeInTheDocument();
  });

  it("tags AI sessions in the list", async () => {
    server.use(
      http.get("*/v1/sessions", () =>
        HttpResponse.json({
          items: [
            { id: "a", title: "Practice", status: "report_ready", created_at: "2026-11-18T10:00:00Z", latest_report_version: null, error_code: null, interview_id: "iv1" },
            { id: "b", title: "Recorded", status: "report_ready", created_at: "2026-11-18T10:00:00Z", latest_report_version: null, error_code: null, interview_id: null },
          ],
        }),
      ),
    );
    renderApp("/sessions", { user: USER });
    const row = (await main().findByRole("link", { name: "Practice" })).closest("li") as HTMLElement;
    expect(within(row).getByText("AI interview")).toBeInTheDocument();
    expect(within((main().getByRole("link", { name: "Recorded" })).closest("li") as HTMLElement).queryByText("AI interview")).toBeNull();
  });
});

describe("picker", () => {
  it("offers every voice with the default preselected, a headphone tip and a mic check", async () => {
    const u = userEvent.setup();
    const track = { stop: vi.fn() };
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) } });
    renderApp("/interviews/new", { user: USER });
    const voice = (await main().findByLabelText("Voice")) as HTMLSelectElement;
    expect(voice.value).toBe("Kore");
    expect(within(voice).getAllByRole("option")).toHaveLength(9);
    expect(main().getByText(/Use headphones/)).toBeInTheDocument();
    await u.click(main().getByRole("button", { name: "Test microphone" }));
    expect(await main().findByText("Microphone works.")).toBeInTheDocument();
    expect(track.stop).toHaveBeenCalled();
  });

  it("preselects the selected scenario's voice, follows scenario changes, and always sends voice", async () => {
    const u = userEvent.setup();
    const bodies: string[] = [];
    const realFetch = globalThis.fetch;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (input instanceof Request && input.method === "POST" && input.url.endsWith("/interviews")) bodies.push(await input.clone().text());
      return realFetch(input, init);
    });
    const { router } = renderApp("/interviews/new", { user: USER });
    const voice = (await main().findByLabelText("Voice")) as HTMLSelectElement;
    expect(voice.value).toBe("Kore"); // first scenario's voice
    await u.click(main().getByRole("radio", { name: /Reluctant patient/ }));
    expect(voice.value).toBe("Leda");
    await u.click(main().getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/interviews\/iv_/));
    expect(JSON.parse(bodies[0]!)).toMatchObject({ scenario_id: "sc_reluctant_patient", voice: "Leda" });
    vi.restoreAllMocks();
  });

  it("explains a denied microphone", async () => {
    const u = userEvent.setup();
    vi.stubGlobal("navigator", { ...navigator, mediaDevices: { getUserMedia: vi.fn(async () => Promise.reject(new Error("no"))) } });
    renderApp("/interviews/new", { user: USER });
    await u.click(await main().findByRole("button", { name: "Test microphone" }));
    expect(await main().findByRole("alert")).toHaveTextContent(/couldn't use your microphone/);
  });

  it("starts with the chosen voice and spends a unit", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await u.selectOptions(await main().findByLabelText("Voice"), "Puck");
    await u.click(main().getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/interviews\/iv_/));
    const iv = mockBackend.getInterview(UID, here(router).split("/")[2]!);
    expect(iv.voice).toBe("Puck");
    expect(mockBackend.getUsage(UID).interview.day.used).toBe(1);
  });

  it("is blocked at the interview cap", async () => {
    mockBackend.configure({ caps: { interview: { day: 0 } } });
    renderApp("/interviews/new", { user: USER });
    expect(await main().findByRole("button", { name: "Start interview" })).toBeDisabled();
    expect(main().getByText(/today's AI interview limit/)).toBeInTheDocument();
  });
});

describe("live interview", () => {
  it("runs picker -> live -> End -> upload -> session page with the linked change goal", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    const fake = lastFakeRelay()!;
    act(() => fake.advance(2)); // AI speaks: frames reach the engine
    expect(engines[0]!.played).toBeGreaterThan(0);
    engines[0]!.onCaptureFrame(new ArrayBuffer(640));
    expect(fake.received).toHaveLength(1);

    await u.click(main().getByRole("button", { name: "End interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
    const sid = here(router).split("/")[2]!;

    const linked = mockBackend.getSession(UID, sid);
    expect(linked.interview_id).toBe(iid);
    expect(mockBackend.getInterview(UID, iid).state).toBe("ended");
    expect(engines[0]!.stopped).toBe(1);
    expect(engines[0]!.closed).toBe(true);
    await waitFor(() => expect(mockBackend.getSession(UID, sid).status).not.toBe("uploading"));
    // the scenario's seeded goal was PUT as a final no-rating card; no setup form on the page
    await waitFor(() => expect(mockBackend.getRating(UID, sid).final).toBeTruthy());
    expect(mockBackend.getRating(UID, sid).final?.card.change_goal).toBe("Book the follow-up visit");
    expect(mockBackend.getRating(UID, sid).final?.no_rating).toBe(true);
    expect(screen.queryByLabelText("Change goal")).not.toBeInTheDocument();
    expect(mockBackend.getUsage(UID).interview.day.used).toBe(1);
  });

  it("End order: create session, read draft, PUT final no-rating goal, then upload", async () => {
    const calls: string[] = [];
    const puts: unknown[] = [];
    server.events.on("request:start", ({ request }) => {
      const u = new URL(request.url);
      const path = u.pathname.replace(/^\/v1/, "").replace(/\/(s|iv)_[^/]+/g, "/:id");
      calls.push(`${request.method} ${path}`);
      if (request.method === "PUT" && path.endsWith("/rating")) void request.clone().json().then((b) => puts.push(b));
    });
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    await u.click(main().getByRole("button", { name: "End interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
    server.events.removeAllListeners();
    const order = calls.filter((c) => /\/sessions$|\/rating$|\/audio$/.test(c));
    expect(order.slice(0, 4)).toEqual(["POST /sessions", "GET /sessions/:id/rating", "PUT /sessions/:id/rating", "POST /sessions/:id/audio"]);
    expect(puts).toEqual([{ final: true, no_rating: true, card: { change_goal: "Book the follow-up visit" } }]);
  });

  it("tolerates 409 rating_final on the goal PUT and goes on to upload", async () => {
    let puts = 0;
    server.use(
      http.put("*/v1/sessions/:id/rating", () => {
        puts++;
        return HttpResponse.json({ status: 409, message: "x", request_id: "r", details: [{ code: "rating_final", message: "x" }] }, { status: 409 });
      }),
    );
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    await u.click(main().getByRole("button", { name: "End interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
    expect(puts).toBe(1);
  });

  it("422 rating_invalid on the goal PUT does not block the upload (session-page fallback handles it)", async () => {
    server.use(
      http.put("*/v1/sessions/:id/rating", () =>
        HttpResponse.json(
          { status: 422, message: "x", request_id: "r", details: [{ code: "rating_invalid", message: "x", field: "change_goal", issue: "too_long" }] },
          { status: 422 },
        ),
      ),
    );
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    await u.click(main().getByRole("button", { name: "End interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
  });

  it("resume after a failed upload tolerates 409 rating_final on the PUT", async () => {
    let audioFails = 1;
    server.use(
      http.post("*/v1/sessions/:id/audio", () => {
        if (audioFails-- > 0) return HttpResponse.json({ error: { code: "internal", message: "x", request_id: "r" } }, { status: 500 });
        return undefined;
      }),
    );
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    await u.click(main().getByRole("button", { name: "End interview" }));
    // first End: PUT done, audio failed -> still on the interview page; retry
    await waitFor(() => expect(audioFails).toBe(0));
    const retry = await screen.findByRole("button", { name: /try again|end interview|evaluate/i });
    await u.click(retry);
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
  });

  it("shows the warning toast at warn_s and auto-Ends at the limit", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const fake = lastFakeRelay()!;
    act(() => fake.advance(480));
    expect(await main().findByTestId("warn-toast")).toHaveTextContent(/2 minutes left/);
    act(() => fake.advance(120)); // time_up, then the relay closes 1000
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
    expect(mockBackend.getSession(UID, here(router).split("/")[2]!).interview_id).toMatch(/^iv_/);
  });

  it("shows reconnecting after a drop, retries the same url, and keeps the recorder running", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const first = lastFakeRelay()!;
    act(() => first.drop());
    expect(await main().findByText(/Reconnecting/)).toBeInTheDocument();
    await waitFor(() => expect(lastFakeRelay()).not.toBe(first), { timeout: 3000 });
    expect(lastFakeRelay()!.url).toBe(first.url);
    await waitFor(() => expect(main().queryByText(/Reconnecting/)).toBeNull());
    expect(main().getByText("Listening")).toBeInTheDocument();
    expect(engines).toHaveLength(1);
    expect(engines[0]!.closed).toBe(false);
    expect(engines[0]!.stopped).toBe(0);
    // only connected time is recorded: paused on the drop, resumed on `ready{resumed:true}` (resume is called on every ready: initial + reconnect; a no-op unless paused)
    expect(engines[0]!.paused).toBe(1);
    expect(engines[0]!.resumed).toBe(2);
  });

  it("flushes queued AI audio on interrupted", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const fake = lastFakeRelay()!;
    act(() => fake.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "interrupted" }) })));
    expect(engines[0]!.flushed).toBe(1);
  });

  it("explains a denied microphone and stays on the start screen", async () => {
    denyMic = true;
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await u.click(await main().findByRole("radio", { name: /Reluctant patient/ }));
    await u.click(main().getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/interviews\/iv_/));
    await u.click(await main().findByRole("button", { name: "Start talking" }));
    expect(await main().findByRole("alert")).toHaveTextContent(/couldn't use your microphone/);
    expect(lastFakeRelay()).toBeUndefined();
  });
});

describe("discard and leave prompt (AC9)", () => {
  it("Discard abandons the interview, uploads nothing, creates no session and returns to /sessions", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    await u.click(main().getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(here(router)).toBe("/sessions"));
    expect(mockBackend.getInterview(UID, iid).state).toBe("abandoned");
    expect(mockBackend.listSessions(UID, {}).items).toHaveLength(0);
    expect(engines[0]!.stopped).toBe(0);
    expect(engines[0]!.closed).toBe(true);
  });

  it("leaving mid-interview asks first: Keep talking stays, Discard leaves without a session", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    await act(() => router.navigate("/settings"));
    const dialog = await screen.findByRole("alertdialog");
    await u.click(within(dialog).getByRole("button", { name: "Keep talking" }));
    expect(here(router)).toBe(`/interviews/${iid}`);
    expect(screen.queryByRole("alertdialog")).toBeNull();

    await act(() => router.navigate("/settings"));
    await u.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(here(router)).toBe("/settings"));
    expect(mockBackend.getInterview(UID, iid).state).toBe("abandoned");
    expect(mockBackend.listSessions(UID, {}).items).toHaveLength(0);
  });

  it("Keep talking returns focus to the element focused before the prompt", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const opener = main().getByRole("button", { name: "Discard" });
    opener.focus();
    await act(() => router.navigate("/settings"));
    const dialog = await screen.findByRole("alertdialog");
    await u.click(within(dialog).getByRole("button", { name: "Keep talking" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("Settings from the account menu: Keep talking returns focus to the account menu trigger", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const trigger = screen.getByRole("button", { name: "Account menu" });
    await u.click(trigger);
    await u.click(await screen.findByRole("menuitem", { name: "Settings" }));
    const dialog = await screen.findByRole("alertdialog");
    await u.click(within(dialog).getByRole("button", { name: "Keep talking" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("falls back to the page heading when the opener is gone", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const gone = document.createElement("button");
    main().getByRole("button", { name: "Discard" }).parentElement!.appendChild(gone);
    gone.focus();
    await act(() => router.navigate("/settings"));
    await screen.findByRole("alertdialog");
    gone.remove();
    await u.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await waitFor(() => expect(screen.getByRole("main").querySelector("h1")).toHaveFocus());
  });

  it("Escape also returns focus to the opener", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const opener = main().getByRole("button", { name: "Discard" });
    opener.focus();
    await act(() => router.navigate("/settings"));
    await screen.findByRole("alertdialog");
    await u.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("Keep talking and Escape are disabled while Discard is in flight, so the leave still proceeds", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    server.use(
      http.post("*/v1/interviews/:id/end", async () => {
        await gate;
        return HttpResponse.json({ ok: true });
      }),
    );
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    await act(() => router.navigate("/settings"));
    const dialog = within(await screen.findByRole("alertdialog"));
    await u.click(dialog.getByRole("button", { name: "Discard" }));
    expect(dialog.getByRole("button", { name: "Keep talking" })).toBeDisabled();
    await u.keyboard("{Escape}");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    release();
    await waitFor(() => expect(here(router)).toBe("/settings"));
    expect(iid).toMatch(/^iv_/);
  });

  it("leaving with Evaluate what I have ends, uploads and opens the session", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    await act(() => router.navigate("/settings"));
    await u.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Evaluate what I have" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
    expect(mockBackend.getSession(UID, here(router).split("/")[2]!).interview_id).toBe(iid);
  });
});

describe("leaving ends the interview (D6)", () => {
  it("warns on tab close/reload while live", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    const ev = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
  });

  it("a fresh page load of a live interview shows Interview ended, ends it, and does not reconnect", async () => {
    const u = userEvent.setup();
    const first = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, first.router);
    mockBackend.setInterviewState(iid, "live"); // the relay marked it live before the page went away
    cleanup();
    resetFakeRelay();
    engines.length = 0;
    renderApp(`/interviews/${iid}`, { user: USER });
    expect(await main().findByText("Interview ended")).toBeInTheDocument();
    await waitFor(() => expect(mockBackend.getInterview(UID, iid).state).toBe("ended"));
    expect(main().queryByRole("button", { name: "Start talking" })).toBeNull();
    expect(lastFakeRelay()).toBeUndefined();
    expect(engines).toHaveLength(0);
  });

  it("Back to your sessions on the ended page goes to /sessions", async () => {
    const u = userEvent.setup();
    const first = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, first.router);
    mockBackend.setInterviewState(iid, "live");
    cleanup();
    resetFakeRelay();
    const { router } = renderApp(`/interviews/${iid}`, { user: USER });
    await u.click(await main().findByRole("link", { name: "Back to your sessions" }));
    await waitFor(() => expect(here(router)).toBe("/sessions"));
  });

  it("Back to your sessions on the load-error card goes to /sessions", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/iv_nope", { user: USER });
    await u.click(await main().findByRole("link", { name: "Back to your sessions" }));
    await waitFor(() => expect(here(router)).toBe("/sessions"));
  });

  it("Not now on the pre-start page goes to /new", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await u.click(await main().findByRole("radio", { name: /Reluctant patient/ }));
    await u.click(main().getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/interviews\/iv_/));
    await u.click(await main().findByRole("link", { name: "Not now" }));
    await waitFor(() => expect(here(router)).toBe("/new"));
  });

  it("Cancel on the scenario picker goes to /new", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await u.click(await main().findByRole("link", { name: "Cancel" }));
    await waitFor(() => expect(here(router)).toBe("/new"));
  });

  it("double Start talking makes one engine and one socket", async () => {
    slowMic = true;
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await u.click(await main().findByRole("radio", { name: /Reluctant patient/ }));
    await u.click(main().getByRole("button", { name: "Start interview" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/interviews\/iv_/));
    await u.dblClick(await main().findByRole("button", { name: "Start talking" }));
    await waitFor(() => expect(lastFakeRelay()?.readyState).toBe(1));
    expect(engines).toHaveLength(1);
  });

  it("says so when the relay ends it without time up", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    await startLive(u, router);
    act(() => lastFakeRelay()!.close(1000));
    expect(await main().findByText(/interview has ended/i)).toBeInTheDocument();
  });
});
