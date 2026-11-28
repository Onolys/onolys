import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getStatusListener, setStatusListener, type SessionStatusDoc } from "../../api/statusListener";
import { mockBackend, mockEmitter, server } from "../../mocks/server";
import { getJob } from "../upload/uploader";
import { here, renderApp } from "../../test/renderApp";

const EMAIL = "rater@clinic.org";
const UID = "u_rater_clinic_org";
const USER = { email: EMAIL, verified: true };

const create = (title?: string) => mockBackend.createSession(UID, { title }).session.id;
const upload = (sid: string) => {
  mockBackend.requestAudio(UID, sid, { content_type: "audio/mpeg", size_bytes: 10, filename_ext: "mp3" });
  mockBackend.completeAudio(UID, sid);
};
const toAwaiting = (sid: string) => {
  upload(sid);
  mockBackend.settle(sid);
};
const open = (sid: string) => renderApp(`/sessions/${sid}`, { user: USER });
const tick = (sid: string) => act(() => void mockBackend.advance(sid));
/** Waits for the first snapshot (the timeline), then returns the live status region. */
const ready = async () => {
  await screen.findByRole("list", { name: "Progress" });
  return screen.getByRole("status");
};
const progress = () => screen.getByRole("list", { name: "Progress" });
const stepItem = (label: string) =>
  within(progress())
    .getAllByRole("listitem")
    .find((li) => li.textContent?.replace(/^✓/, "").startsWith(label))!;

let getCalls: string[] = [];
beforeEach(() => {
  getCalls = [];
  server.events.on("request:start", ({ request }) => {
    const u = new URL(request.url);
    if (request.method === "GET" && /\/v1\/sessions\/[^/]+$/.test(u.pathname)) getCalls.push(u.pathname);
  });
});
afterEach(() => {
  server.events.removeAllListeners();
  setStatusListener(mockEmitter);
});

const failedDoc = (sid: string, code: string): SessionStatusDoc => ({
  uid: UID,
  state: "failed",
  step: null,
  progress: 40,
  error_code: code,
  latest_report_version: null,
  updated_at: new Date().toISOString(),
  transcript_ready: true,
  speaker_confirmed: true,
  rating_submitted: true,
  has_rating: true,
});

describe("session page: navigation and heading", () => {
  it("uses the session name in the heading", async () => {
    const sid = create("Walking practice");
    await open(sid);
    expect(await screen.findByRole("heading", { level: 1, name: "Session - Walking practice" })).toBeInTheDocument();
  });

  it("falls back to the first 20 characters of the saved change goal", async () => {
    const sid = create();
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "Walk outside every afternoon" } });
    await open(sid);
    expect(await screen.findByRole("heading", { level: 1, name: "Session - Walk outside every a…" })).toBeInTheDocument();
  });

  it("opens an existing completed session directly as its report", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    mockBackend.settle(sid);
    const { router } = await open(sid);
    await waitFor(() => expect(here(router)).toBe(`/sessions/${sid}/reports/1`));
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("uses the completed detail response when the status listener has not answered", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    mockBackend.settle(sid);
    setStatusListener({ subscribe: () => () => {} });
    const { router } = await open(sid);
    await waitFor(() => expect(here(router)).toBe(`/sessions/${sid}/reports/1`));
  });

  it("keeps whole Unicode characters in the change-goal heading", async () => {
    const sid = create();
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: `${"🙂".repeat(19)}🧠hello` } });
    await open(sid);
    expect(await screen.findByRole("heading", { level: 1, name: `Session - ${"🙂".repeat(19)}🧠…` })).toBeInTheDocument();
  });

  it("keeps cancel below the steps and does not offer deletion before a report", async () => {
    const sid = create();
    await open(sid);
    await ready();
    const cancel = screen.getByRole("button", { name: "Cancel session" });
    expect(progress().compareDocumentPosition(cancel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete session" })).not.toBeInTheDocument();
  });
});

describe("session page: status listener", () => {
  it("attaches to the status doc and follows it while loading session metadata", async () => {
    const sid = create();
    await open(sid);
    expect(await screen.findByRole("heading", { level: 1, name: "Session" })).toBeInTheDocument();
    expect(await ready()).toHaveTextContent("Getting ready to upload your recording.");
    act(() => void mockBackend.requestAudio(UID, sid, { content_type: "audio/mpeg", size_bytes: 1, filename_ext: "mp3" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Uploading your recording."));
    act(() => void mockBackend.completeAudio(UID, sid));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Checking your audio."));
    tick(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Transcribing the recording."));
    expect(stepItem("Transcribe")).toHaveTextContent(/in progress/i);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(getCalls).toContain(`/v1/sessions/${sid}`);
  });

  it("names what is missing in awaiting_input: both, then each one", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    const status = await ready();
    await waitFor(() => {
      expect(status).toHaveTextContent("Confirm who the clinician is");
      expect(status).toHaveTextContent("Waiting for your change goal");
    });
    act(() => void mockBackend.confirmSpeaker(UID, sid, "spk_0"));
    await waitFor(() => expect(status).not.toHaveTextContent("Confirm who the clinician is"));
    expect(status).toHaveTextContent("Waiting for your change goal");
  });

  it("shows run sub-labels, the stay-or-leave copy and elapsed time, then links the report", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    await open(sid);
    await ready();
    expect(screen.queryByText(/close this tab/)).not.toBeInTheDocument();
    act(() => void mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    expect(screen.getByText(/You can close this tab/)).toBeInTheDocument();
    expect(screen.getByText(/Elapsed \d+:\d\d/)).toBeInTheDocument();
    tick(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Writing tips"));
    act(() => mockBackend.settle(sid));
    await screen.findByRole("heading", { level: 1, name: "Report" });
    // flag off: no card, no fallback (submitted); no submit buttons, no Run again
    expect(screen.queryByRole("textbox", { name: "Change goal" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit rating|no rating/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run again/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Your rating is final/)).not.toBeInTheDocument();
  });

  it("does not poll GET /sessions/{id} while a session runs", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    await open(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    for (let i = 0; i < 3; i++) {
      tick(sid);
      await new Promise((r) => setTimeout(r, 60));
    }
    expect(getCalls).toEqual([`/v1/sessions/${sid}`]);
  });

  it("on a listener error polls the detail and resubscribes; no stopped notice until retries run out", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    await ready();
    act(() => mockEmitter.emitError(sid, new Error("permission-denied")));
    await waitFor(() => expect(getCalls).toHaveLength(1));
    expect(screen.getByRole("status")).toHaveTextContent("Confirm who the clinician is");
    expect(screen.queryByText(/live updates stopped/i)).not.toBeInTheDocument();
    // the listener resubscribes (1 s backoff) and live updates resume
    act(() => void mockBackend.confirmSpeaker(UID, sid, "spk_0"));
    await waitFor(() => expect(screen.getByRole("status")).not.toHaveTextContent("Confirm who the clinician is"), { timeout: 3000 });
  });

  it("shows a friendly not-found card when the fallback GET is a 404", async () => {
    // The heading shows on DOM commit, before the passive effect attaches the listener. Emitting
    // earlier is silently dropped (no fallback GET, no alert), so wait for the subscription itself.
    let subscribed = 0;
    const inner = getStatusListener();
    setStatusListener({
      subscribe(id, a, b) {
        subscribed++;
        return inner.subscribe(id, a, b);
      },
    });
    await open("s_nope");
    await screen.findByRole("heading", { level: 1, name: "Session" });
    await waitFor(() => expect(subscribed).toBeGreaterThanOrEqual(1));
    act(() => mockEmitter.emitError("s_nope", new Error("permission-denied")));
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(/we couldn't find this session/i);
    expect(card).not.toHaveTextContent(/upload/i);
    expect(screen.getByRole("link", { name: /back to your sessions/i })).toHaveAttribute("href", "/sessions");
  });

  it("an unknown session id ends in the not-found card, not an endless spinner (E21)", async () => {
    await open("s_nope");
    const card = await screen.findByRole("alert", undefined, { timeout: 4000 });
    expect(card).toHaveTextContent(/we couldn't find this session/i);
    expect(card).not.toHaveTextContent(/upload/i);
  });

  it("a malformed session id (422 invalid_parameters) shows the same not-found card (E21)", async () => {
    server.use(
      http.get("*/v1/sessions/:id", () =>
        HttpResponse.json(
          { schema_version: "0.0.1", status: 422, message: "x", details: [{ code: "invalid_parameters", message: "x" }], request_id: "req_422" },
          { status: 422 },
        ),
      ),
    );
    await open("not-hex");
    const card = await screen.findByRole("alert", undefined, { timeout: 4000 });
    expect(card).toHaveTextContent(/we couldn't find this session/i);
    expect(card).not.toHaveTextContent(/upload/i);
  });

  it("unsubscribes when the user leaves the page", async () => {
    const sid = create();
    const inner = getStatusListener();
    let active = 0;
    setStatusListener({
      subscribe(id, a, b) {
        active++;
        const off = inner.subscribe(id, a, b);
        return () => {
          active--;
          off();
        };
      },
    });
    const { router } = await open(sid);
    await ready();
    expect(active).toBe(1);
    await act(() => router.navigate("/settings"));
    expect(active).toBe(0);
  });
});

describe("session page: slots", () => {
  it("renders the upload slot while uploading and the speaker gate when needed, no rating card", async () => {
    const sid = create();
    await open(sid);
    await ready();
    expect(document.querySelector('[data-slot="upload"]')).not.toBeNull();
    expect(document.querySelector('[data-slot="speaker-gate"]')).toBeNull();
    upload(sid);
    act(() => mockBackend.settle(sid));
    await waitFor(() => expect(document.querySelector('[data-slot="speaker-gate"]')).not.toBeNull());
    expect(document.querySelector('[data-slot="upload"]')).toBeNull();
    act(() => void mockBackend.confirmSpeaker(UID, sid, "spk_0"));
    await waitFor(() => expect(document.querySelector('[data-slot="speaker-gate"]')).toBeNull());
  });
});

describe("session page: rating slot (flag off) and fallback", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("renders no card and no #rating-globals-* with the flag off", async () => {
    const sid = create();
    await open(sid);
    await ready();
    expect(document.querySelector('[data-slot="rating-card"]')).toBeNull();
    expect(document.querySelector('[id^="rating-globals-"]')).toBeNull();
    expect(screen.queryByRole("button", { name: /submit rating|no rating/i })).not.toBeInTheDocument();
  });

  it("shows the Continue fallback for an unsubmitted session, prefilled from the draft, PUT only", async () => {
    const sid = create();
    mockBackend.putRating(UID, sid, { final: false, card: { change_goal: "Draft goal" } }); // draft, read via GET /rating
    await open(sid);
    const field = await screen.findByLabelText("Change goal");
    await waitFor(() => expect(field).toHaveValue("Draft goal"));
    expect(document.querySelector('[data-slot="rating-fallback"]')).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(mockBackend.getRating(UID, sid).final).toBeTruthy());
    await waitFor(() => expect(screen.queryByLabelText("Change goal")).not.toBeInTheDocument());
  });

  it("shows the fallback with an empty field when there is no draft, and blocks a blank goal", async () => {
    const sid = create();
    await open(sid);
    const field = await screen.findByLabelText("Change goal");
    expect(field).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/required/i);
    expect(mockBackend.getRating(UID, sid).final).toBeFalsy();
  });

  it("does not show the fallback once submitted", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    await open(sid);
    await ready();
    expect(document.querySelector('[data-slot="rating-fallback"]')).toBeNull();
    expect(screen.queryByLabelText("Change goal")).not.toBeInTheDocument();
  });

  it("shows the original card with the flag on, and no fallback", async () => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    const sid = create();
    await open(sid);
    await ready();
    expect(document.querySelector('[data-slot="rating-card"]')).not.toBeNull();
    expect(document.querySelector('[data-slot="rating-fallback"]')).toBeNull();
    await waitFor(() => expect(document.querySelector('[id^="rating-globals-"]')).not.toBeNull());
  });
});

describe("session page: upload incomplete", () => {
  const incompleteDoc = (): SessionStatusDoc => ({
    ...failedDoc("x", "x"),
    state: "upload_incomplete",
    error_code: null,
    transcript_ready: false,
    speaker_confirmed: false,
    rating_submitted: false,
    has_rating: false,
    progress: 5,
  });

  afterEach(() => vi.unstubAllGlobals());

  it("offers Resume upload (pick the file again) and Delete; resuming registers a new upload", async () => {
    vi.stubGlobal(
      "Audio",
      class {
        duration = 15 * 60;
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
    const sid = create();
    await open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, incompleteDoc()));
    expect(await screen.findByText(/upload didn't finish/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete session" })).not.toBeInTheDocument();
    const resume = screen.getByRole("button", { name: "Resume upload" });
    expect(resume).toBeDisabled();
    await userEvent.upload(
      screen.getByLabelText(/audio recording/i),
      new File([new Uint8Array(10)], "visit.mp3", { type: "audio/mpeg" }),
    );
    await waitFor(() => expect(resume).toBeEnabled());
    await userEvent.click(resume);
    await waitFor(() => expect(getJob(sid)).toBeDefined());
    // the same-origin mock PUT may already have completed (validating); either way a new upload was registered
    expect(mockBackend.getSession(UID, sid).status).toMatch(/^(uploading|validating)$/);
  });
});

describe("session page: failure cards", () => {
  const withKind = (sid: string, code: string, extra: Record<string, unknown>): SessionStatusDoc =>
    ({ ...failedDoc(sid, code), ...extra }) as SessionStatusDoc;
  const show = async (extra: Record<string, unknown>, code = "upstream_unavailable") => {
    const sid = create();
    await open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, withKind(sid, code, extra)));
    return { sid, card: await screen.findByRole("alert") };
  };

  it("a failed session offers Delete (every kind), which confirms and returns to the list", async () => {
    const sid = create();
    const { router } = await open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, withKind(sid, "upstream_unavailable", { error_kind: "transient", retries_left: 2 })));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Delete session" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(here(router)).toBe("/sessions"));
  });

  it("a permanently failed session also offers Delete", async () => {
    const { card } = await show({ error_kind: "permanent_internal" }, "internal");
    expect(card).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete session" })).toBeInTheDocument();
  });

  it("the in-progress steps view never offers Delete", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    await ready();
    for (const state of ["created", "validating", "transcribing", "awaiting_input", "running"] as const) {
      act(() => mockEmitter.emit(sid, { ...failedDoc(sid, "x"), state, error_code: null }));
      await screen.findByRole("list", { name: "Progress" });
      expect(screen.queryByRole("button", { name: "Delete session" })).not.toBeInTheDocument();
    }
  });

  it("transient with retries left: message, not-counted sentence, Reference, disabled Retry (5)", async () => {
    const { sid, card } = await show({ error_kind: "transient", retries_left: 2, counted: false });
    expect(card).toHaveTextContent(/busy right now/i);
    expect(card).toHaveTextContent("This did not count toward your limit.");
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).getByRole("button", { name: "Retry (5)" })).toHaveAttribute("aria-disabled", "true");
    expect(within(card).queryByRole("link", { name: /Start a new session|Upload a different file/ })).not.toBeInTheDocument();
  });

  it("Retry enables after 5 s and POSTs /sessions/{id}/retry", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let posts = 0;
      server.use(
        http.post("*/v1/sessions/:id/retry", () => {
          posts += 1;
          return HttpResponse.json({ session_id: "x" }, { status: 202 });
        }),
      );
      const { card } = await show({ error_kind: "transient", retries_left: 1 });
      await act(async () => void vi.advanceTimersByTime(5000));
      const btn = within(card).getByRole("button", { name: "Retry" });
      await act(async () => btn.click());
      await waitFor(() => expect(posts).toBe(1));
    } finally {
      vi.useRealTimers();
    }
  });

  it("Retry unlocks again when a failed->failed snapshot changes retries_left after a successful retry", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let posts = 0;
      server.use(
        http.post("*/v1/sessions/:id/retry", () => {
          posts += 1;
          return HttpResponse.json({ session_id: "x" }, { status: 202 });
        }),
      );
      const { sid, card } = await show({ error_kind: "transient", retries_left: 2 });
      await act(async () => void vi.advanceTimersByTime(5000));
      await act(async () => within(card).getByRole("button", { name: "Retry" }).click());
      await waitFor(() => expect(posts).toBe(1));
      // locked while the successful POST waits for the status doc to move
      await waitFor(() => expect(within(card).getByRole("button", { name: /Retry/ })).toHaveAttribute("aria-disabled", "true"));
      act(() => mockEmitter.emit(sid, withKind(sid, "upstream_unavailable", { error_kind: "transient", retries_left: 1 })));
      await act(async () => void vi.advanceTimersByTime(5000));
      await waitFor(() =>
        expect(within(screen.getByRole("alert")).getByRole("button", { name: "Retry" })).not.toHaveAttribute("aria-disabled", "true"),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("transient at retries_left=0: several-tries copy and a new-session CTA, no Retry", async () => {
    const { sid, card } = await show({ error_kind: "transient", retries_left: 0 });
    expect(card).toHaveTextContent("We couldn't finish this after several tries. Start a new session.");
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).getByRole("link", { name: "Start a new session" })).toHaveAttribute("href", "/sessions/new");
    expect(within(card).queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });

  it("permanent_internal: our-side copy, new-session CTA, no Retry", async () => {
    const { sid, card } = await show({ error_kind: "permanent_internal", retries_left: 0 }, "internal_error");
    expect(card).toHaveTextContent(
      "Something went wrong on our side. This did not count toward your limit. Please start a new session.",
    );
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).getByRole("link", { name: "Start a new session" })).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });

  it.each([
    ["unsupported_audio", /can't use this file type/i],
    ["audio_unreadable", /couldn't read this audio file/i],
    ["no_speech", /couldn't hear enough speech in this recording/i],
    ["speakers_not_separated", /couldn't tell the two speakers apart in this recording/i],
    ["transcription_failed", /Transcription didn't finish/i],
  ] as const)("user_file %s: per-code text, Reference, Upload a different file", async (code, message) => {
    const { sid, card } = await show({ error_kind: "user_file", retries_left: 0, counted: false }, code);
    expect(card).toHaveTextContent(message);
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).getByRole("link", { name: "Upload a different file" })).toHaveAttribute(
      "href",
      `/sessions/new?from=${sid}`,
    );
    expect(card).not.toHaveTextContent("counted toward your limit");
    expect(within(card).queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });

  it("user_file with counted=true appends the counted sentence", async () => {
    const { card } = await show({ error_kind: "user_file", retries_left: 0, counted: true }, "no_speech");
    expect(card).toHaveTextContent("This counted toward your limit.");
  });

  it("unknown code and no kind falls back to permanent_internal copy", async () => {
    const { sid, card } = await show({}, "some_new_code");
    expect(card).toHaveTextContent(/on our side/);
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();
  });

  it("shows the API's message when Retry itself fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      server.use(
        http.post("*/v1/sessions/:id/retry", () =>
          HttpResponse.json(
            { schema_version: "0.0.1", status: 409, message: "x", details: [{ code: "invalid_state", message: "x" }], request_id: "req_abc123" },
            { status: 409 },
          ),
        ),
      );
      const { card } = await show({ error_kind: "transient", retries_left: 1 });
      await act(async () => void vi.advanceTimersByTime(5000));
      await act(async () => within(card).getByRole("button", { name: "Retry" }).click());
      await waitFor(() => {
        const text = screen.getAllByRole("alert").map((a) => a.textContent).join(" ");
        expect(text).toMatch(/isn't possible at this stage/i);
        expect(text).toContain("Reference: req_abc123");
      });
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("session page: interview-linked first run (free, works at a full eval cap)", () => {
  const heldAtCap = (linked: boolean) => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    if (linked) {
      server.use(
        http.get("*/v1/sessions/:id", ({ params }) =>
          HttpResponse.json({ ...mockBackend.getSession(UID, String(params.id)), interview_id: "iv1", free_run: true }),
        ),
      );
    }
    return sid;
  };

  it("keeps Start enabled at a full eval cap for an interview-linked session", async () => {
    const sid = heldAtCap(true);
    await open(sid);
    await ready();
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(getCalls.length).toBeGreaterThan(0)); // the detail (interview_id) loads
    await waitFor(() => expect(start).toBeEnabled());
  });

  it("still disables Start at a full eval cap for a normal session", async () => {
    const sid = heldAtCap(false);
    await open(sid);
    await ready();
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(start).toBeDisabled());
  });
});

describe("session page: free_run gates Start (review round 2)", () => {
  const detailOverride = (freeRun: boolean) =>
    server.use(
      http.get("*/v1/sessions/:id", ({ params }) =>
        HttpResponse.json({
          ...mockBackend.getSession(UID, String(params.id)),
          interview_id: "iv1",
          free_run: freeRun,
        }),
      ),
    );

  it("a free interview session held by concurrent_runs keeps Start enabled while cached usage is at the cap", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    detailOverride(true);
    const { queryClient } = await open(sid);
    queryClient.setQueryData(["usage"], mockBackend.getUsage(UID));
    await ready();
    act(() =>
      mockEmitter.emit(sid, { ...failedDoc(sid, "concurrent_runs"), state: "awaiting_input", progress: 20 }),
    );
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(getCalls.length).toBeGreaterThan(0)); // the detail (free_run) loads
    await waitFor(() => expect(start).toBeEnabled());
  });

  it("a voided interview session (free_run false) held at the daily cap keeps Start disabled", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    detailOverride(false);
    const { queryClient } = await open(sid);
    queryClient.setQueryData(["usage"], mockBackend.getUsage(UID));
    await ready();
    act(() =>
      mockEmitter.emit(sid, { ...failedDoc(sid, "daily_cap_reached"), state: "awaiting_input", progress: 20 }),
    );
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(getCalls.length).toBeGreaterThan(0));
    await waitFor(() => expect(start).toBeDisabled());
  });
});

describe("session page: start held by an active run", () => {
  it("shows the concurrent message with Start enabled, not the daily limit or reset time", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    await ready();
    act(() =>
      mockEmitter.emit(sid, {
        ...failedDoc(sid, "concurrent_runs"),
        state: "awaiting_input",
        progress: 20,
        has_rating: true,
      }),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "You already have a rating running. Wait for it to finish.",
      ),
    );
    expect(screen.getByRole("status")).not.toHaveTextContent(/limit|start the rating after/i);
    expect(await screen.findByRole("button", { name: "Start" })).toBeEnabled();
  });
});

describe("transcript speaker gate", () => {
  it.each([false, true])("shows detected labels only when roles are missing (confirmed=%s)", async (confirmed) => {
    const sid = create();
    mockBackend.putTranscript(UID, sid, {
      turns: [
        { id: "t1", speaker: "Alex", role: confirmed ? "clinician" : null, text: "Let's talk about walking." },
        { id: "t2", speaker: "Sam", role: confirmed ? "client" : null, text: "I want to walk more." },
      ],
    });
    await open(sid);
    await ready();
    if (confirmed) {
      expect(screen.queryByRole("heading", { name: "Who is the clinician?" })).toBeNull();
    } else {
      expect(await screen.findByRole("heading", { name: "Speaker Alex" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Speaker Sam" })).toBeInTheDocument();
      expect(screen.getByText("Let's talk about walking.")).toBeInTheDocument();
    }
  });
});

describe("session page: upload failed", () => {
  const stub = (code: string): SessionStatusDoc =>
    ({ ...failedDoc("x", code), state: "upload_failed", progress: 0, transcript_ready: false, speaker_confirmed: false, rating_submitted: false, has_rating: false }) as unknown as SessionStatusDoc;

  it("shows UploadFailedView (reason, way back, Reference) when the status is upload_failed", async () => {
    const sid = create();
    await open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, stub("audio_too_long")));
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent("Upload failed: This recording is longer than 20 minutes. Upload a shorter one. Choose a different file.");
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(screen.getByRole("link", { name: /choose a different file/i })).toHaveAttribute("href", "/sessions/new");
    expect(screen.queryByRole("button", { name: /delete session/i })).not.toBeInTheDocument();
  });

  it("a stale link whose stub exists shows the same view", async () => {
    // The status listener's first snapshot is the stub doc (the session itself is gone: GET would 404).
    setStatusListener({
      subscribe(_id, onStatus) {
        queueMicrotask(() => onStatus(stub("audio_unreadable")));
        return () => {};
      },
    });
    await open("s_gone");
    expect(await screen.findByRole("alert")).toHaveTextContent(/^Upload failed: We couldn't read this audio file/);
  });

  it("a stale link without a stub shows generic not-found copy (no upload blame, C7) with a way to start a new session", async () => {
    await open("s_nope");
    const card = await screen.findByRole("alert", undefined, { timeout: 4000 });
    expect(card).toHaveTextContent("We couldn't find this session. It may have been deleted, or the link may be mistyped.");
    expect(card).not.toHaveTextContent(/upload/i);
    expect(screen.getByRole("link", { name: /start a new session/i })).toHaveAttribute("href", "/sessions/new");
  });
});

describe("session page: cancel", () => {
  const link = () => screen.getByRole("button", { name: "Cancel session" });
  const confirm = async () => {
    await userEvent.click(link());
    const dlg = await screen.findByRole("alertdialog", { name: "Cancel this session?" });
    return dlg;
  };
  const confirmBtn = (dlg: HTMLElement) => within(dlg).getByRole("button", { name: "Cancel session" });

  it("link is blue with red hover and shown only in the seven states", async () => {
    const sid = create();
    await open(sid);
    await ready();
    expect(link()).toHaveClass("text-primary", "hover:text-destructive");
    for (const state of ["report_ready", "failed", "cancelled"] as const) {
      act(() => mockEmitter.emit(sid, { ...failedDoc(sid, "x"), state }));
      await waitFor(() => expect(screen.queryByRole("button", { name: "Cancel session" })).not.toBeInTheDocument());
    }
  });

  it("variant A copy before transcription, variant B once it started", async () => {
    const sid = create();
    upload(sid);
    await open(sid);
    await ready();
    let dlg = await confirm();
    expect(dlg).toHaveTextContent("Your upload stays until you delete the session. This won't count toward your limit.");
    await userEvent.click(within(dlg).getByRole("button", { name: "Keep processing" }));
    tick(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Transcribing the recording."));
    dlg = await confirm();
    expect(dlg).toHaveTextContent("Transcription has started, so this counts toward your daily limit.");
  });

  it("confirm shows Cancelling… with a spinner, then the not-counted message", async () => {
    const sid = create();
    upload(sid);
    let release!: () => void;
    server.use(
      http.post("*/v1/sessions/:id/cancel", async () => {
        await new Promise<void>((r) => (release = r));
        return HttpResponse.json(mockBackend.cancelSession(UID, sid));
      }),
    );
    await open(sid);
    await ready();
    await userEvent.click(confirmBtn(await confirm()));
    const busy = await screen.findByRole("button", { name: /Cancelling…/ });
    expect(busy).toBeDisabled();
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(busy.querySelector('[data-slot="spinner"]')).not.toBeNull();
    act(() => release());
    expect(await screen.findByRole("heading", { name: "Cancelled" })).toBeInTheDocument();
    expect(screen.getByText("Session cancelled. This did not count toward your limit.")).toBeInTheDocument();
  });

  it("a counted cancel says so, and a reload shows the persisted message", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    await ready();
    await userEvent.click(confirmBtn(await confirm()));
    expect(await screen.findByText("Session cancelled. This counted toward your limit.")).toBeInTheDocument();
    cleanup();
    await open(sid);
    expect(await screen.findByText("Session cancelled. This counted toward your limit.")).toBeInTheDocument();
  });

  it("the cancelled view offers Delete, and no rating, speaker gate, retry or cancel link", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    await ready();
    await userEvent.click(confirmBtn(await confirm()));
    await screen.findByRole("heading", { name: "Cancelled" });
    expect(screen.getByRole("button", { name: "Delete session" })).toBeInTheDocument();
    for (const name of [/cancel session/i, /start/i, /retry/i, /submit/i, /confirm/i]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("heading", { name: /rating|speaker/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Progress" })).not.toBeInTheDocument();
    expect(screen.queryByText(/retry/i)).not.toBeInTheDocument();
  });

  it("deleting a cancelled session confirms, calls DELETE and returns to the list", async () => {
    const sid = create();
    toAwaiting(sid);
    const { router } = await open(sid);
    await ready();
    await userEvent.click(confirmBtn(await confirm()));
    await screen.findByRole("heading", { name: "Cancelled" });
    await userEvent.click(screen.getByRole("button", { name: "Delete session" }));
    expect(screen.getByRole("alertdialog", { name: "Delete this session?" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(here(router)).toBe("/sessions"));
    expect(() => mockBackend.getSession(UID, sid)).toThrow();
  });

  it("an omitted counted shows no sentence", async () => {
    const sid = create();
    await open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, { ...failedDoc(sid, "x"), state: "cancelled", counted: null }));
    expect(await screen.findByRole("heading", { name: "Cancelled" })).toBeInTheDocument();
    expect(screen.queryByText(/Session cancelled/)).not.toBeInTheDocument();
  });

  it("a 500 shows the error card with Reference and the link returns", async () => {
    const sid = create();
    upload(sid);
    server.use(http.post("*/v1/sessions/:id/cancel", () => new HttpResponse(null, { status: 500 })));
    await open(sid);
    await ready();
    await userEvent.click(confirmBtn(await confirm()));
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent("We couldn't cancel this session. Try again.");
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(link()).toBeEnabled();
    expect(screen.queryByRole("heading", { name: "Cancelled" })).not.toBeInTheDocument();
  });

  it("a 409 shows the already-finished copy and the page follows the live status", async () => {
    const sid = create();
    upload(sid);
    server.use(
      http.post("*/v1/sessions/:id/cancel", () =>
        HttpResponse.json({ schema_version: "0.0.1", status: 409, message: "x", details: [{ code: "invalid_state", message: "x" }], request_id: "r" }, { status: 409 }),
      ),
    );
    const { router } = await open(sid);
    await ready();
    await userEvent.click(confirmBtn(await confirm()));
    expect(await screen.findByRole("alert")).toHaveTextContent("This session already finished or failed.");
    act(() => mockEmitter.emit(sid, { ...failedDoc(sid, "x"), state: "report_ready", latest_report_version: 1 }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Cancel session" })).not.toBeInTheDocument());
    await waitFor(() => expect(here(router)).toBe(`/sessions/${sid}/reports/1`));
  });
});

describe("session page: processing screen", () => {
  const emit = (sid: string, patch: Partial<SessionStatusDoc>) =>
    act(() => mockEmitter.emit(sid, { ...failedDoc(sid, "x"), error_code: null, ...patch } as SessionStatusDoc));
  const bar = () => screen.queryByRole("progressbar", { name: "Overall progress" });
  const slot = () => document.querySelector('[data-slot="cancel"]');
  const CANCELLABLE = ["created", "uploading", "upload_incomplete", "validating", "transcribing", "awaiting_input", "running"] as const;

  it("shows the hint per phase, outside the live region", async () => {
    const sid = create();
    await open(sid);
    const status = await ready();
    const cases: [SessionStatusDoc["state"], RegExp][] = [
      ["created", /Keep this tab open until upload finishes/],
      ["uploading", /Keep this tab open until upload finishes/],
      ["validating", /You can close this tab/],
      ["transcribing", /You can close this tab/],
      ["running", /You can close this tab/],
      ["awaiting_input", /We'll wait here for your choice/],
    ];
    for (const [state, re] of cases) {
      emit(sid, { state });
      expect(await screen.findByText(re)).toBeInTheDocument();
      expect(status).not.toHaveTextContent(re);
      expect(screen.getAllByText(re)).toHaveLength(1);
    }
    for (const state of ["report_ready", "failed"] as const) {
      emit(sid, { state });
      await waitFor(() => expect(screen.queryByText(/close this tab|Keep this tab open|wait here/)).not.toBeInTheDocument());
    }
  });

  it("shows bar, N% and Elapsed from created through transcribing; none at report_ready, failed, cancelled", async () => {
    const sid = create();
    await open(sid);
    await ready();
    const startedAt = new Date(Date.now() - 65_000).toISOString();
    for (const state of ["created", "uploading", "transcribing"] as const) {
      emit(sid, { state, progress: 10, started_at: startedAt, stage_started_at: startedAt, progress_next: 40 });
      await waitFor(() => expect(state && bar()).toBeInTheDocument());
      expect(screen.getByText(/^\d+%$/)).toBeInTheDocument();
      expect(screen.getByText(/Elapsed \d+:\d\d/)).toBeInTheDocument();
    }
    for (const state of ["report_ready", "failed", "cancelled"] as const) {
      emit(sid, { state, progress: 100 });
      await waitFor(() => expect(bar()).not.toBeInTheDocument());
      expect(screen.queryByText(/^\d+%$/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Elapsed/)).not.toBeInTheDocument();
    }
  });

  it("bar has an accessible name, value and valuetext, outside the live region", async () => {
    const sid = create();
    await open(sid);
    const status = await ready();
    emit(sid, { state: "awaiting_input", progress: 40 });
    await waitFor(() => expect(bar()).toBeInTheDocument());
    expect(bar()).toHaveAttribute("value", "40");
    expect(bar()).toHaveAttribute("max", "100");
    expect(bar()).toHaveAttribute("aria-valuetext", "40 percent");
    expect(status.contains(bar())).toBe(false);
    expect(status.closest("[aria-live]")?.contains(bar())).toBeFalsy();
  });

  it("marks the current step with In progress, a spinner and the accent; done has a check; pending is muted", async () => {
    const sid = create();
    await open(sid);
    await ready();
    emit(sid, { state: "transcribing", progress: 20, transcript_ready: false, speaker_confirmed: false, rating_submitted: false });
    await waitFor(() => expect(stepItem("Transcribe")).toHaveAttribute("data-status", "current"));
    const cur = stepItem("Transcribe");
    expect(within(cur).getByText("In progress")).toBeVisible();
    expect(cur).toHaveClass("text-primary", "border-primary");
    expect(cur.querySelector('[data-slot="spinner"]')).not.toBeNull();
    const done = stepItem("Upload");
    expect(done).toHaveClass("text-score-good");
    expect(done.querySelector('[data-slot="step-check"]')).not.toBeNull();
    expect(stepItem("Report")).toHaveClass("text-muted-foreground");
    emit(sid, { state: "failed", error_code: "transcription_failed", transcript_ready: false });
    await waitFor(() => expect(stepItem("Transcribe")).toHaveAttribute("data-status", "failed"));
    expect(stepItem("Transcribe")).toHaveClass("text-destructive");
  });

  it("spinner honours reduced motion: spin is motion-safe only", async () => {
    const sid = create();
    await open(sid);
    await ready();
    emit(sid, { state: "transcribing" });
    await waitFor(() => expect(stepItem("Transcribe").querySelector('[data-slot="spinner"]')).not.toBeNull());
    const tokens = stepItem("Transcribe").querySelector('[data-slot="spinner"]')!.className.split(/\s+/);
    expect(tokens).not.toContain("animate-spin");
    expect(tokens).toContain("motion-safe:animate-spin");
  });

  it("keeps the live-region text unchanged across ticks and progress changes", async () => {
    const sid = create();
    await open(sid);
    const status = await ready();
    const startedAt = new Date(Date.now() - 65_000).toISOString();
    emit(sid, { state: "transcribing", progress: 20, progress_next: 40, started_at: startedAt, stage_started_at: startedAt });
    await waitFor(() => expect(status).toHaveTextContent("Transcribing the recording."));
    const elapsed = () => screen.getByText(/Elapsed \d+:\d\d/).textContent;
    const before = elapsed();
    let mutations = 0;
    const obs = new MutationObserver((m) => (mutations += m.length));
    obs.observe(status, { subtree: true, childList: true, characterData: true, attributes: true });
    await waitFor(() => expect(elapsed()).not.toBe(before), { timeout: 3000 });
    emit(sid, { state: "transcribing", progress: 30, progress_next: 40, started_at: startedAt, stage_started_at: startedAt });
    await waitFor(() => expect(Number(bar()!.getAttribute("value"))).toBeGreaterThanOrEqual(30));
    obs.disconnect();
    expect(mutations).toBe(0);
    expect(status).toHaveTextContent("Transcribing the recording.");
  });

  it("renders the cancel slot (right-aligned, below the steps) for every cancellable state and no other", async () => {
    const sid = create();
    await open(sid);
    await ready();
    for (const state of CANCELLABLE) {
      emit(sid, { state });
      await waitFor(() => expect(slot()).not.toBeNull());
      expect(slot()).toHaveClass("justify-end");
      expect(within(slot() as HTMLElement).getByRole("button", { name: "Cancel session" })).toBeInTheDocument();
      expect(progress().compareDocumentPosition(slot()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    for (const state of ["report_ready", "failed"] as const) {
      emit(sid, { state });
      await waitFor(() => expect(slot()).toBeNull());
    }
  });

  it("has no inline spinner SVG or hand-rolled spin class in the session screen", () => {
    const files = import.meta.glob(["./*.tsx", "!./*.test.tsx"], { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    for (const [name, src] of Object.entries(files)) {
      expect(src, name).not.toMatch(/(?<!motion-safe:)\banimate-spin\b/);
      expect(src, name).not.toMatch(/<svg[^>]*(spin|spinner)/i);
    }
    expect(files["./CancelLink.tsx"]).toContain("Spinner");
  });
});


describe("session page: input locks", () => {
  it.each(["running", "failed", "report_ready"] as const)("locks an unsubmitted rating and hides the unconfirmed speaker gate in %s", async (state) => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    await screen.findByRole("list", { name: "Speakers" });
    act(() => mockEmitter.emit(sid, { ...failedDoc(sid, "x"), state, speaker_confirmed: false, rating_submitted: false }));
    await waitFor(() => expect(document.querySelector('[data-slot="speaker-gate"]')).toBeNull());
    expect(await screen.findByLabelText("Change goal")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Submit rating" })).not.toBeInTheDocument();
    vi.unstubAllEnvs();
  });
});
