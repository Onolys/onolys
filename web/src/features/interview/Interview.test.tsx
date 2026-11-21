/**
 * SP10 Task 11: landing cards, picker, live page, End -> upload -> session, warn toast, reconnect, discard (AC9).
 * MSW serves /v1, the fake relay plays the socket, the audio engine is a stub (no browser audio in jsdom).
 */
import { act, screen, waitFor, within } from "@testing-library/react";
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
    expect(await interviewCard.findByText("5 of 5 left today")).toBeInTheDocument();
    expect(interviewCard.getByText("30 of 30 left this month")).toBeInTheDocument();
    const rate = within(main().getByRole("region", { name: "Rate a recording" }));
    expect(rate.getByText("20 of 20 left today")).toBeInTheDocument();
    expect(rate.getByRole("link", { name: "New session" })).toHaveAttribute("href", "/sessions/new");
    await u.click(interviewCard.getByRole("link", { name: "Start AI Interview" }));
    expect(here(router)).toBe("/interviews/new");
  });

  it.each([
    ["day", { interview: { day: 0 } }, /today's AI interview limit\. It resets at/],
    ["month", { interview: { month: 0 } }, /this month's AI interview limit\. It resets on/],
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
    renderApp("/", { user: USER });
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
    expect(await screen.findByLabelText("Change goal")).toHaveValue("Book the follow-up visit");
    expect(mockBackend.getUsage(UID).interview.day.used).toBe(1);
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
    // only connected time is recorded: paused on the drop, resumed on `ready{resumed:true}`
    expect(engines[0]!.paused).toBe(1);
    expect(engines[0]!.resumed).toBe(1);
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
  it("Discard abandons the interview, uploads nothing, creates no session and returns home", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    await u.click(main().getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(here(router)).toBe("/"));
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
    const dialog = await screen.findByRole("dialog");
    await u.click(within(dialog).getByRole("button", { name: "Keep talking" }));
    expect(here(router)).toBe(`/interviews/${iid}`);
    expect(screen.queryByRole("dialog")).toBeNull();

    await act(() => router.navigate("/settings"));
    await u.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(here(router)).toBe("/settings"));
    expect(mockBackend.getInterview(UID, iid).state).toBe("abandoned");
    expect(mockBackend.listSessions(UID, {}).items).toHaveLength(0);
  });

  it("leaving with Evaluate what I have ends, uploads and opens the session", async () => {
    const u = userEvent.setup();
    const { router } = renderApp("/interviews/new", { user: USER });
    const iid = await startLive(u, router);
    await act(() => router.navigate("/settings"));
    await u.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Evaluate what I have" }));
    await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
    expect(mockBackend.getSession(UID, here(router).split("/")[2]!).interview_id).toBe(iid);
  });
});
