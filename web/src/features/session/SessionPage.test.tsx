import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
    .find((li) => li.textContent?.startsWith(label))!;

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

describe("session page: status listener", () => {
  it("attaches to the status doc and follows it with no GET /sessions/{id}", async () => {
    const sid = create();
    open(sid);
    expect(await screen.findByRole("heading", { level: 1, name: "Session" })).toBeInTheDocument();
    expect(await ready()).toHaveTextContent("Getting ready to upload your recording.");
    act(() => void mockBackend.requestAudio(UID, sid, { content_type: "audio/mpeg", size_bytes: 1, filename_ext: "mp3" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Uploading your recording."));
    act(() => void mockBackend.completeAudio(UID, sid));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Checking your audio."));
    tick(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Transcribing the recording."));
    expect(stepItem("Check audio")).toHaveTextContent(/done/i);
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(getCalls).toEqual([]);
  });

  it("names what is missing in awaiting_input: both, then each one", async () => {
    const sid = create();
    toAwaiting(sid);
    open(sid);
    const status = await ready();
    await waitFor(() => {
      expect(status).toHaveTextContent("Confirm who the clinician is");
      expect(status).toHaveTextContent("Waiting for your rating");
    });
    act(() => void mockBackend.confirmSpeaker(UID, sid, "spk_0"));
    await waitFor(() => expect(status).not.toHaveTextContent("Confirm who the clinician is"));
    expect(status).toHaveTextContent("Waiting for your rating");
  });

  it("shows run sub-labels, the stay-or-leave copy and elapsed time, then links the report", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    open(sid);
    await ready();
    expect(screen.queryByText(/Usually under 5 minutes/)).not.toBeInTheDocument();
    act(() => void mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Rating the session"));
    expect(screen.getByText(/Usually under 5 minutes/)).toBeInTheDocument();
    expect(screen.getByText(/Elapsed \d+:\d\d/)).toBeInTheDocument();
    tick(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Checking your reasons"));
    act(() => mockBackend.settle(sid));
    const link = await screen.findByRole("link", { name: /view report/i });
    expect(link).toHaveAttribute("href", `/sessions/${sid}/reports/1`);
    // FX45: the rating is final now: read-only, no submit buttons, no Run again
    expect(screen.getByRole("textbox", { name: "Change goal" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /submit rating|no rating/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run again/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Your rating is final/)).toBeInTheDocument();
  });

  it("does not poll GET /sessions/{id} while a session runs", async () => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    open(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Rating the session"));
    for (let i = 0; i < 3; i++) {
      tick(sid);
      await new Promise((r) => setTimeout(r, 60));
    }
    expect(getCalls).toEqual([]);
  });

  it("on a listener error polls the detail and resubscribes; no stopped notice until retries run out", async () => {
    const sid = create();
    toAwaiting(sid);
    open(sid);
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
    open("s_nope");
    await screen.findByRole("heading", { level: 1, name: "Session" });
    await waitFor(() => expect(subscribed).toBeGreaterThanOrEqual(1));
    act(() => mockEmitter.emitError("s_nope", new Error("permission-denied")));
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(/couldn't find that/i);
    expect(screen.getByRole("link", { name: /back to your sessions/i })).toHaveAttribute("href", "/");
  });

  it("an unknown session id ends in the not-found card, not an endless spinner (E21)", async () => {
    open("s_nope");
    const card = await screen.findByRole("alert", undefined, { timeout: 4000 });
    expect(card).toHaveTextContent(/couldn't find that/i);
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
    open("not-hex");
    const card = await screen.findByRole("alert", undefined, { timeout: 4000 });
    expect(card).toHaveTextContent(/couldn't find that/i);
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
    const { router } = open(sid);
    await ready();
    expect(active).toBe(1);
    await act(() => router.navigate("/settings"));
    expect(active).toBe(0);
  });
});

describe("session page: slots", () => {
  it("renders the rating card slot always, the upload slot while uploading and the speaker gate when needed", async () => {
    const sid = create();
    open(sid);
    await ready();
    expect(document.querySelector('[data-slot="rating-card"]')).not.toBeNull();
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

describe("session page: upload incomplete (D4)", () => {
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
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, incompleteDoc()));
    expect(await screen.findByText(/upload didn't finish/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete session" })).toBeInTheDocument();
    const resume = screen.getByRole("button", { name: "Resume upload" });
    expect(resume).toBeDisabled();
    await userEvent.upload(
      screen.getByLabelText(/audio recording/i),
      new File([new Uint8Array(10)], "visit.mp3", { type: "audio/mpeg" }),
    );
    await waitFor(() => expect(resume).toBeEnabled());
    await userEvent.click(resume);
    await waitFor(() => expect(getJob(sid)).toBeDefined());
    expect(mockBackend.getSession(UID, sid).status).toBe("uploading");
  });
});

describe("session page: error cards", () => {
  const UPLOAD_NEW = [
    ["unsupported_audio", /can't use this file type/i],
    ["audio_too_long", /longer than 20 minutes/i],
    ["audio_too_large", /over 300 MB/i],
    ["audio_unreadable", /couldn't read this audio file/i],
    ["no_speech", /couldn't hear enough speech in this recording/i],
    ["speakers_not_separated", /couldn't tell the two speakers apart in this recording/i],
    ["transcription_failed", /Transcription didn't finish/i],
  ] as const;
  const TRY_AGAIN = [
    ["rating_invalid", /needs a change/i],
    ["upstream_unavailable", /busy right now/i],
    ["daily_cap_reached", /reached today's limit/i],
    ["concurrent_runs", /already have a rating running/i],
    ["email_unverified", /verify your email/i],
    ["invalid_state", /isn't possible at this stage/i],
    ["rate_limited", /a little fast/i],
    ["internal_error", /something went wrong/i],
    ["some_new_code", /something went wrong/i],
  ] as const;

  it.each(UPLOAD_NEW)("%s: message, reference id and a new-upload recovery", async (code, message) => {
    const sid = create();
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, { ...failedDoc(sid, code), transcript_ready: false, speaker_confirmed: false, rating_submitted: false }));
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(message);
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).getByRole("link", { name: "Upload a different file" })).toHaveAttribute(
      "href",
      `/sessions/new?from=${sid}`,
    );
    expect(within(card).queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it.each(TRY_AGAIN)("%s: message, reference id and Try again", async (code, message) => {
    const sid = create();
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, failedDoc(sid, code)));
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(message);
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    expect(within(card).getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(within(card).queryByRole("link", { name: "Upload a different file" })).not.toBeInTheDocument();
  });

  it.each(["internal_error", "upstream_unavailable"])("%s before a transcript offers a new upload, not Try again (BH2)", async (code) => {
    const sid = create();
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, { ...failedDoc(sid, code), transcript_ready: false, speaker_confirmed: false, rating_submitted: false }));
    const card = await screen.findByRole("alert");
    expect(within(card).getByRole("link", { name: "Upload a different file" })).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("Try again starts a new run and the timeline moves on", async () => {
    const user = userEvent.setup();
    const sid = create("fail-paudit");
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    mockBackend.settle(sid);
    open(sid);
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(/something went wrong/i);
    await user.click(within(card).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Rating the session"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps Try again locked after a successful POST until the session state changes (W15)", async () => {
    const user = userEvent.setup();
    const sid = create();
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, failedDoc(sid, "internal_error")));
    let posts = 0;
    server.use(
      http.post("*/v1/sessions/:id/runs", () => {
        posts += 1;
        return HttpResponse.json({ session_id: sid }, { status: 202 });
      }),
    );
    const btn = await screen.findByRole("button", { name: "Try again" });
    await user.click(btn);
    await waitFor(() => expect(posts).toBe(1));
    await waitFor(() => expect(btn).toBeDisabled());
    await user.click(btn);
    expect(posts).toBe(1);
  });

  it("shows the API's message and request id when Try again itself fails", async () => {
    const user = userEvent.setup();
    const sid = create();
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, failedDoc(sid, "internal_error")));
    server.use(
      http.post("*/v1/sessions/:id/runs", () =>
        HttpResponse.json(
          {
            schema_version: "0.0.1",
            status: 503,
            message: "x",
            details: [{ code: "upstream_unavailable", message: "x" }],
            request_id: "req_abc123",
          },
          { status: 503 },
        ),
      ),
    );
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    const alerts = await screen.findAllByRole("alert");
    const text = alerts.map((a) => a.textContent).join(" ");
    expect(text).toMatch(/busy right now/i);
    expect(text).toContain("Reference: req_abc123");
  });

  it("cap reached at auto-start shows the limit message with Start, and Start runs", async () => {
    const user = userEvent.setup();
    const sid = create("cap-held");
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    open(sid);
    const status = await ready();
    await waitFor(() => expect(status).toHaveTextContent(/You've reached today's limit\. You can start the rating after .+\./));
    await user.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Rating the session"));
  });

  it("disables Try again and Start with the reset time when today's runs are used up", async () => {
    const sid = create("cap-held");
    toAwaiting(sid);
    mockBackend.confirmSpeaker(UID, sid, "spk_0");
    mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
    mockBackend.configure({ caps: { eval: { day: 1 } } });
    const other = create();
    toAwaiting(other);
    mockBackend.confirmSpeaker(UID, other, "spk_0");
    mockBackend.putRating(UID, other, { final: true, no_rating: true, card: { change_goal: "g" } }); // uses the one run
    open(sid);
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(start).toBeDisabled());
    expect(screen.getByRole("status")).toHaveTextContent(/start the rating after/i);

    act(() => mockEmitter.emit(sid, failedDoc(sid, "internal_error")));
    const run = await screen.findByRole("button", { name: "Try again" });
    await waitFor(() => expect(run).toBeDisabled());
    expect(screen.getByRole("alert")).toHaveTextContent(/after .+/i);
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
          HttpResponse.json({ ...mockBackend.getSession(UID, String(params.id)), interview_id: "iv1" }),
        ),
      );
    }
    return sid;
  };

  it("keeps Start enabled at a full eval cap for an interview-linked session", async () => {
    const sid = heldAtCap(true);
    open(sid);
    await ready();
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(getCalls.length).toBeGreaterThan(0)); // the detail (interview_id) loads
    await waitFor(() => expect(start).toBeEnabled());
  });

  it("still disables Start at a full eval cap for a normal session", async () => {
    const sid = heldAtCap(false);
    open(sid);
    await ready();
    const start = await screen.findByRole("button", { name: "Start" });
    await waitFor(() => expect(start).toBeDisabled());
  });
});

describe("session page: Try again after a failed free interview run (review R1)", () => {
  const failedAtCap = (freeRun: boolean) => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    server.use(
      http.get("*/v1/sessions/:id", ({ params }) =>
        HttpResponse.json({
          ...mockBackend.getSession(UID, String(params.id)),
          interview_id: "iv1",
          free_run: freeRun,
        }),
      ),
    );
    return sid;
  };

  it("keeps Try again enabled at a full eval cap when the failed run was free", async () => {
    const sid = failedAtCap(true);
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, failedDoc(sid, "internal_error")));
    const run = await screen.findByRole("button", { name: "Try again" });
    await waitFor(() => expect(getCalls.length).toBeGreaterThan(0)); // the detail (free_run) loads
    await waitFor(() => expect(run).toBeEnabled());
    expect(screen.getByRole("alert")).not.toHaveTextContent(/reached today's limit/i);
  });

  it("still disables Try again at a full eval cap when the interview's free run was voided", async () => {
    const sid = failedAtCap(false);
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, failedDoc(sid, "internal_error")));
    const run = await screen.findByRole("button", { name: "Try again" });
    await waitFor(() => expect(getCalls.length).toBeGreaterThan(0));
    await waitFor(() => expect(run).toBeDisabled());
  });
});

describe("session page: period-aware caps", () => {
  it.each([
    [{ eval: { day: 0 } }, /reached today's limit/i],
  ] as const)("disables Try again with the matching message for caps %j", async (caps, message) => {
    const sid = create();
    toAwaiting(sid);
    mockBackend.configure({ caps });
    open(sid);
    await ready();
    act(() => mockEmitter.emit(sid, failedDoc(sid, "internal_error")));
    const run = await screen.findByRole("button", { name: "Try again" });
    await waitFor(() => expect(run).toBeDisabled());
    expect(screen.getByRole("alert")).toHaveTextContent(message);
  });
});

describe("session page: delete", () => {
  it("asks first, says what is removed, and cancel keeps the session", async () => {
    const user = userEvent.setup();
    const sid = create();
    open(sid);
    await ready();
    await user.click(screen.getByRole("button", { name: "Delete session" }));
    const dialog = await screen.findByRole("dialog", { name: /delete this session/i });
    expect(dialog).toHaveTextContent(/audio, transcript, rating and all report versions/i);
    expect(dialog).toHaveTextContent(/permanently/i);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(() => mockBackend.getSession(UID, sid)).not.toThrow();
  });

  it("confirm deletes and goes to the dashboard without a not-found flash", async () => {
    const user = userEvent.setup();
    const sid = create();
    const { router } = open(sid);
    await ready();
    await user.click(screen.getByRole("button", { name: "Delete session" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete permanently" }));
    await screen.findByRole("heading", { level: 1, name: "Sessions" });
    expect(here(router)).toBe("/");
    expect(() => mockBackend.getSession(UID, sid)).toThrow();
    expect(getCalls).toEqual([]);
  });

  it("keeps the dialog open with an error when delete fails", async () => {
    const user = userEvent.setup();
    const sid = create();
    open(sid);
    await ready();
    server.use(
      http.delete("*/v1/sessions/:id", () =>
        HttpResponse.json(
          { schema_version: "0.0.1", status: 500, message: "x", details: [{ code: "internal_error", message: "x" }], request_id: "req_del" },
          { status: 500 },
        ),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Delete session" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(within(dialog).getByRole("alert")).toHaveTextContent("Reference: req_del"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("Escape is ignored while a delete is in flight, so a failure is still shown (W32)", async () => {
    const user = userEvent.setup();
    const sid = create();
    open(sid);
    await ready();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    server.use(
      http.delete("*/v1/sessions/:id", async () => {
        await gate;
        return HttpResponse.json(
          { schema_version: "0.0.1", status: 500, message: "x", details: [{ code: "internal_error", message: "x" }], request_id: "req_esc" },
          { status: 500 },
        );
      }),
    );
    await user.click(screen.getByRole("button", { name: "Delete session" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Delete permanently" })).toBeDisabled());
    fireEvent.keyDown(dialog, { key: "Escape" }); // focus can still be inside the dialog (e.g. on Cancel)
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    release();
    await waitFor(() => expect(within(dialog).getByRole("alert")).toHaveTextContent("Reference: req_esc"));
  });

  it("Escape closes the dialog", async () => {
    const user = userEvent.setup();
    const sid = create();
    open(sid);
    await ready();
    await user.click(screen.getByRole("button", { name: "Delete session" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

