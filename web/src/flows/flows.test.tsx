/**
 * SP05 Task 14: end-to-end flow tests (PRD R9, D12, AC2, AC9, AC10). Every flow starts at a route, drives the real
 * router and pages through user-visible steps, and MSW serves /v1 from the in-memory mock backend. The only
 * out-of-band moves are the ones the real worker does: `mockBackend.advance` stands in for transcription/run stages,
 * `service.markVerified` for clicking the email link. Page-level detail lives next to each page; these tests cover
 * the journeys across pages.
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockBackend, server } from "../mocks/server";
import { here, renderApp } from "../test/renderApp";

const EMAIL = "rater@clinic.org";
const UID = "u_rater_clinic_org";
const USER = { email: EMAIL, verified: true };

/**
 * jsdom's XMLHttpRequest is not intercepted by MSW (and would hit the network), so the upload PUT goes through a
 * thin XHR stand-in that sends the same method, URL, headers and body with fetch, which MSW serves. The mock
 * handler pins Content-Type like the signed URL, so a wrong header still fails the upload.
 */
class FetchXhr {
  status = 0;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
  private method = "";
  private url = "";
  private headers: Record<string, string> = {};
  private ctl = new AbortController();
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  send(body: Blob) {
    this.upload.onprogress?.({ lengthComputable: true, loaded: body.size / 2, total: body.size });
    fetch(this.url, { method: this.method, headers: this.headers, body, signal: this.ctl.signal }).then(
      (r) => {
        this.status = r.status;
        this.upload.onprogress?.({ lengthComputable: true, loaded: body.size, total: body.size });
        this.onload?.();
      },
      () => (this.ctl.signal.aborted ? this.onabort?.() : this.onerror?.()),
    );
  }
  abort() {
    this.ctl.abort();
  }
}

beforeEach(() => {
  vi.stubGlobal("XMLHttpRequest", FetchXhr);
  // jsdom never loads media metadata; report a 15 minute recording.
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
});
afterEach(() => {
  vi.unstubAllGlobals();
  server.events.removeAllListeners();
  localStorage.clear();
  sessionStorage.clear();
});

/** Turn the rating UI on for a describe block (the card, the "Rating the session" copy and the comparison report). */
const withRatingOn = () => {
  beforeEach(() => vi.stubEnv("VITE_RATING_ENABLED", "true"));
  afterEach(() => vi.unstubAllEnvs());
};

const user = () => userEvent.setup();
const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });
const nav = (name: string) => within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name });
const mp3 = () => new File([new Uint8Array(100)], "visit.mp3", { type: "audio/mpeg" });
const sessionId = (router: Parameters<typeof here>[0]) => here(router).split("/")[2]!;
const step = (sid: string) => act(() => void mockBackend.advance(sid));
const settle = (sid: string) => act(() => mockBackend.settle(sid));

/** Dashboard -> New session -> choose file -> Start; ends on /sessions/:id. */
async function uploadViaUi(u: ReturnType<typeof user>, router: Parameters<typeof here>[0], title?: string) {
  await u.click(nav("New Session"));
  await h1("Welcome rater");
  await u.click(within(screen.getByRole("main")).getByRole("link", { name: "New session" }));
  await h1("New session");
  if (title) await u.type(screen.getByLabelText(/title/i), title);
  // default (flag off): the one required setup field; with the rating UI on it lives on the session card instead
  const goal = screen.queryByLabelText("Change goal");
  if (goal) await u.type(goal, "Walk more in the evenings");
  await u.upload(screen.getByLabelText(/audio recording/i), mp3());
  await u.click(screen.getByRole("button", { name: /start/i }));
  await waitFor(() => expect(here(router)).toMatch(/^\/sessions\/(?!new)[^/]+$/));
  const sid = sessionId(router);
  await h1("Session");
  await waitFor(() => expect(mockBackend.getSession(UID, sid).status).not.toBe("uploading"));
  return sid;
}
/** Fill the rating card with a goal (and optionally Cultivating Change Talk) and submit it. */
async function rateViaUi(u: ReturnType<typeof user>, score?: string) {
  await u.type(await screen.findByLabelText("Change goal"), "Walk more in the evenings");
  if (score) await u.selectOptions(screen.getByLabelText("Cultivating Change Talk score"), score);
  await u.click(screen.getByRole("button", { name: "Submit rating" }));
  await screen.findByText(/Rating submitted\./);
}
/** Transcription done (worker steps), then confirm the first speaker on the gate. */
async function confirmSpeakerViaUi(u: ReturnType<typeof user>, sid: string) {
  settle(sid); // validating -> transcribing -> awaiting_input
  const list = await screen.findByRole("list", { name: "Speakers" });
  const cards = within(list).getAllByRole("listitem").filter((li) => li.parentElement === list);
  await u.click(within(cards[0]).getByRole("button", { name: "This is the clinician" }));
  await waitFor(() => expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument());
}

describe("flow: one submit, no rating card (default)", () => {
  it("sign-up, verify, goal + audio, Start, confirm speaker, coding, then a report without comparison", async () => {
    const u = user();
    const { router, service } = renderApp("/signup");
    await h1("Sign up");
    await u.type(screen.getByLabelText("Email"), EMAIL);
    await u.type(screen.getByLabelText("Password"), "longenough1");
    await u.type(screen.getByLabelText("Confirm password"), "longenough1");
    await u.click(screen.getByRole("button", { name: "Create account" }));
    await h1("Verify your email");
    service.markVerified(EMAIL);
    await u.click(screen.getByRole("button", { name: "I've verified" }));
    await h1("Welcome rater");

    const sid = await uploadViaUi(u, router, "Visit 3");
    expect(screen.queryByLabelText("Cultivating Change Talk score")).toBeNull();
    expect(screen.queryByRole("button", { name: /submit rating|no rating/i })).toBeNull();
    expect(mockBackend.getSession(UID, sid).flags.rating_submitted).toBe(true);
    step(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/transcrib/i));
    await confirmSpeakerViaUi(u, sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    expect(screen.getByRole("status")).not.toHaveTextContent(/rating the session/i);
    settle(sid);
    await u.click(await screen.findByRole("link", { name: "View report" }));
    await waitFor(() => expect(here(router)).toBe(`/sessions/${sid}/reports/1`));
    await h1("Report");
    const glance = await screen.findByRole("region", { name: "At a glance" });
    expect(within(glance).getByText("Cultivating Change Talk")).toBeInTheDocument();
    expect(within(glance).queryByText(/differs|Difference/)).toBeNull();
    expect(within(glance).queryByRole("columnheader", { name: /^You$/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "Where Onolys disagrees" })).toBeNull();
    expect(screen.queryByRole("button", { name: /run again|edit my rating|submit/i })).toBeNull();
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(1);
  });

  it("system failure, then Try again re-runs", async () => {
    const u = user();
    const { router } = renderApp("/sessions", { user: USER });
    await h1("Sessions");
    const sid = await uploadViaUi(u, router, "fail-code");
    await confirmSpeakerViaUi(u, sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    settle(sid);
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    await u.click(within(card).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(2);
  });
});

describe("flow (rating on): sign-up, verify, upload, speaker + rating during transcription, report (AC2, AC9)", () => {
  withRatingOn();
  it("runs end to end, and the submitted rating is final (no edit, no Run again)", async () => {
    const u = user();
    const { router, service } = renderApp("/signup");
    await h1("Sign up");
    await u.type(screen.getByLabelText("Email"), EMAIL);
    await u.type(screen.getByLabelText("Password"), "longenough1");
    await u.type(screen.getByLabelText("Confirm password"), "longenough1");
    await u.click(screen.getByRole("button", { name: "Create account" }));
    await h1("Verify your email");
    expect(screen.getByText(/spam/i)).toBeInTheDocument();
    expect(service.calls.verificationEmails).toBe(1);

    // not verified yet: the app stays put and explains
    await u.click(screen.getByRole("button", { name: "I've verified" }));
    expect(await screen.findByRole("status")).toHaveTextContent("haven't seen your verification");
    service.markVerified(EMAIL);
    await u.click(screen.getByRole("button", { name: "I've verified" }));
    await h1("Welcome rater");
    await u.click(nav("Sessions"));
    await h1("Sessions");
    expect(await screen.findByRole("link", { name: "Start a new session" })).toBeInTheDocument(); // empty state

    const sid = await uploadViaUi(u, router, "Visit 3");
    expect(screen.getByRole("status")).not.toHaveTextContent(/start the rating|limit/i);

    // rating card filled while transcription runs; a rating alone does not start the run
    expect(mockBackend.getSession(UID, sid).status).toBe("validating");
    await rateViaUi(u, "3");
    expect(mockBackend.getSession(UID, sid).flags.rating_submitted).toBe(true);
    step(sid);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/transcrib/i));

    await confirmSpeakerViaUi(u, sid); // run starts by itself once speaker + rating are in
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    settle(sid);
    await u.click(await screen.findByRole("link", { name: "View report" }));
    await waitFor(() => expect(here(router)).toBe(`/sessions/${sid}/reports/1`));
    await h1("Report");
    const glance = await screen.findByRole("region", { name: "At a glance" });
    expect(within(glance).getByText("Cultivating Change Talk")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Feedback: ideas to try" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Behaviour counts" })).toBeInTheDocument();

    // FX45: the report is final: no Run again, no rating edit, a single version
    expect(screen.queryByRole("button", { name: /run again|edit my rating|submit/i })).toBeNull();
    const select = screen.getByLabelText("Version");
    expect(within(select).getAllByRole("option")).toHaveLength(1);
    await u.click(nav("Sessions"));
    await u.click(await screen.findByRole("link", { name: /Visit 3/ }));
    await h1("Session");
    expect(await screen.findByRole("textbox", { name: "Change goal" })).toBeDisabled();
    expect(screen.getByText(/Your rating is final/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run again|submit rating|no rating/i })).toBeNull();
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(1);
  });
});

describe("flow (rating on): no-rating run is final too (AC3)", () => {
  withRatingOn();
  it("shows an Onolys-only report and offers no way to add a rating or run again", async () => {
    const u = user();
    const { router } = renderApp("/sessions", { user: USER });
    await h1("Sessions");
    const sid = await uploadViaUi(u, router);
    await confirmSpeakerViaUi(u, sid);
    await u.type(await screen.findByLabelText("Change goal"), "Walk more in the evenings");
    await u.click(screen.getByRole("button", { name: /No rating/ }));
    await screen.findByText(/Saved without a rating/);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    settle(sid);
    await u.click(await screen.findByRole("link", { name: "View report" }));
    await h1("Report");
    const glance = within(await screen.findByRole("region", { name: "At a glance" }));
    expect(glance.getByText("Cultivating Change Talk")).toBeInTheDocument();
    expect(glance.queryByText(/differs/)).toBeNull();
    expect(screen.queryByRole("region", { name: "Where Onolys disagrees" })).toBeNull();

    expect(screen.queryByRole("button", { name: /run again|edit my rating/i })).toBeNull();
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(1);
  });
});

describe("flow (rating on): system failure, then Try again (AC6a)", () => {
  withRatingOn();
  it("shows the failure card with a reference id, Try again re-runs the same rating", async () => {
    const u = user();
    const { router } = renderApp("/sessions", { user: USER });
    await h1("Sessions");
    const sid = await uploadViaUi(u, router, "fail-code");
    await confirmSpeakerViaUi(u, sid);
    await rateViaUi(u);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    settle(sid); // code stage fails
    const card = await screen.findByRole("alert");
    expect(card).toHaveTextContent(/something went wrong/i);
    expect(card).toHaveTextContent(`Reference: ${sid}`);
    await u.click(within(card).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    const runs = mockBackend.listRuns(UID, sid);
    expect(runs).toHaveLength(2);
    expect(runs[1].rating_id).toBe(runs[0].rating_id); // the same submission
  });
});

describe("flow (rating on): daily cap reached at auto-start, then Start (AC6a)", () => {
  withRatingOn();
  it("says so with the reset time; Start runs once allowed", async () => {
    const u = user();
    const { router } = renderApp("/sessions", { user: USER });
    await h1("Sessions");
    const sid = await uploadViaUi(u, router, "cap-held");
    await rateViaUi(u);
    await confirmSpeakerViaUi(u, sid);
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/You've reached today's limit\. You can start the rating after .+\./),
    );
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(0);
    await u.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Coding the session"));
    settle(sid);
    await u.click(await screen.findByRole("link", { name: "View report" }));
    await waitFor(() => expect(here(router)).toBe(`/sessions/${sid}/reports/1`));
  });
});

describe("flow: delete a session (AC2)", () => {
  it("dashboard -> session -> confirm delete -> dashboard without it", async () => {
    const u = user();
    const sid = mockBackend.createSession(UID, { title: "Doomed visit" }).session.id;
    const { router } = renderApp("/sessions", { user: USER });
    await u.click(await screen.findByRole("link", { name: /Doomed visit/ }));
    await h1("Session");
    expect(here(router)).toBe(`/sessions/${sid}`);
    await u.click(await screen.findByRole("button", { name: "Delete session" }));
    await u.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Delete permanently" }));
    await h1("Sessions"); // delete lands on the sessions list
    expect(here(router)).toBe("/sessions");
    await screen.findByText(/Onolys codes a recorded session/i); // the empty state (the cards also say "New session")
    expect(screen.queryByRole("link", { name: /Doomed visit/ })).toBeNull();
    expect(() => mockBackend.getSession(UID, sid)).toThrow();
  });
});

describe("flow: API key is shown once (AC7)", () => {
  it("secret visible in the modal only; gone after Done and after leaving and coming back; not stored or logged", async () => {
    const u = user();
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => {}));
    try {
      renderApp("/sessions", { user: USER });
      await h1("Sessions");
      await u.click(screen.getByRole("button", { name: "Account menu" }));
      await u.click(screen.getByRole("menuitem", { name: "Settings" }));
      await h1("Settings");
      await u.click(await screen.findByRole("button", { name: "Create API key" }));
      const dialog = await screen.findByRole("dialog");
      const secret = (await within(dialog).findByTestId("api-secret")).textContent ?? "";
      expect(secret).toMatch(/^onolys_[A-Za-z0-9]+_[A-Za-z0-9]+$/);
      await u.click(within(dialog).getByRole("checkbox", { name: /i've stored it/i }));
      await u.click(within(dialog).getByRole("button", { name: "Done" }));
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.body.textContent).not.toContain(secret);

      await u.click(nav("Sessions"));
      await h1("Sessions");
      await u.click(screen.getByRole("button", { name: "Account menu" }));
      await u.click(screen.getByRole("menuitem", { name: "Settings" }));
      await h1("Settings");
      expect(await screen.findByText(/active/i)).toBeInTheDocument();
      expect(document.body.textContent).not.toContain(secret);
      expect(JSON.stringify({ l: { ...localStorage }, s: { ...sessionStorage } })).not.toContain(secret);
      expect(JSON.stringify(spies.flatMap((s) => s.mock.calls))).not.toContain(secret);
    } finally {
      spies.forEach((s) => s.mockRestore());
    }
  });
});

describe("flow: sample report works with no network (AC3a)", () => {
  it("login -> Sample report renders the report and transcript, with zero requests", async () => {
    const requests: string[] = [];
    server.events.on("request:start", ({ request }) => void requests.push(request.url));
    const { router } = renderApp("/login");
    await h1("Log in");
    // opens in a new tab (target=_blank), so assert the link, then the public route
    const sample = within(screen.getByRole("contentinfo")).getByRole("link", { name: "Sample report" });
    expect(sample).toHaveAttribute("href", "/sample");
    expect(sample).toHaveAttribute("target", "_blank");
    await act(() => router.navigate("/sample"));
    await h1("Sample report");
    expect(here(router)).toBe("/sample");
    expect(await screen.findByRole("region", { name: "At a glance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open coded transcript" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /run again/i })).toBeNull();
    expect(requests).toEqual([]);
  });
});

