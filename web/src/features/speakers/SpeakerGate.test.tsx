import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, onTestFinished } from "vitest";
import { mockBackend, server } from "../../mocks/server";
import { renderApp } from "../../test/renderApp";

const UID = "u_rater_clinic_org";
const USER = { email: "rater@clinic.org", verified: true };

const create = (title?: string) => mockBackend.createSession(UID, { title }).session.id;
const toAwaiting = (sid: string) => {
  mockBackend.requestAudio(UID, sid, { content_type: "audio/mpeg", size_bytes: 10, filename_ext: "mp3" });
  mockBackend.completeAudio(UID, sid);
  mockBackend.settle(sid);
};
const open = (sid: string) => renderApp(`/sessions/${sid}`, { user: USER });
const cards = async () => {
  const ul = await screen.findByRole("list", { name: "Speakers" });
  return within(ul)
    .getAllByRole("listitem")
    .filter((li) => li.parentElement === ul);
};
/** A session whose first run is finished, so the report is ready and the clinician can be changed. */
const reportReady = (title?: string) => {
  const sid = create(title);
  toAwaiting(sid);
  mockBackend.confirmSpeaker(UID, sid, "spk_0");
  mockBackend.putRating(UID, sid, { final: true, no_rating: true, card: { change_goal: "g" } });
  mockBackend.settle(sid);
  return sid;
};

describe("speaker gate", () => {
  it("is hidden until the transcript is ready", async () => {
    const sid = create();
    open(sid);
    await screen.findByRole("list", { name: "Progress" });
    expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument();
  });

  it("2 speakers: a card each with 3 sample lines and no 'everyone else' note", async () => {
    const sid = create();
    toAwaiting(sid);
    open(sid);
    const list = await cards();
    expect(list).toHaveLength(2);
    for (const c of list) {
      expect(within(c).getAllByRole("listitem")).toHaveLength(3);
      expect(within(c).getByRole("button", { name: "This is the clinician" })).toBeEnabled();
    }
    expect(screen.queryByText(/everyone else is the client/i)).not.toBeInTheDocument();
  });

  it("3 speakers: all listed, with the 'everyone else is the client' note", async () => {
    const sid = create("three-speakers");
    toAwaiting(sid);
    open(sid);
    expect(await cards()).toHaveLength(3);
    expect(screen.getByText(/everyone else is the client/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "This is the clinician" })).toHaveLength(3);
  });

  it("confirm posts the chosen speaker and the gate goes away", async () => {
    const user = userEvent.setup();
    const sid = create();
    toAwaiting(sid);
    open(sid);
    const list = await cards();
    await user.click(within(list[1]).getByRole("button", { name: "This is the clinician" }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument());
    expect(mockBackend.getSpeakers(UID, sid).clinician_speaker).toBe("spk_1");
  });

  it("shows friendly numbered labels, never the raw speaker id (C9)", async () => {
    const sid = create();
    toAwaiting(sid);
    open(sid);
    const list = await cards();
    expect(within(list[0]).getByRole("heading", { level: 3, name: "Speaker 1" })).toBeInTheDocument();
    expect(within(list[1]).getByRole("heading", { level: 3, name: "Speaker 2" })).toBeInTheDocument();
    expect(screen.queryByText(/spk_\d/)).not.toBeInTheDocument();
  });

  it("stays locked after a successful confirm until the status doc moves on (LM-16)", async () => {
    const user = userEvent.setup();
    const sid = create();
    toAwaiting(sid);
    let posts = 0;
    // The API accepts but the status doc has not moved yet: the gate must not re-enable.
    server.use(
      http.post("*/v1/sessions/:id/speakers/confirm", () => {
        posts++;
        return HttpResponse.json({ schema_version: "0.0.1", session: { id: sid, status: "awaiting_input" }, clinician_speaker: "spk_0" }, { status: 202 });
      }),
    );
    open(sid);
    const list = await cards();
    await user.click(within(list[0]).getByRole("button", { name: "This is the clinician" }));
    await waitFor(() => expect(posts).toBe(1));
    await act(async () => {});
    for (const b of screen.getAllByRole("button", { name: "This is the clinician" })) expect(b).toBeDisabled();
  });

  it("works from the keyboard", async () => {
    const user = userEvent.setup();
    const sid = create();
    toAwaiting(sid);
    open(sid);
    const list = await cards();
    const btn = within(list[0]).getByRole("button", { name: "This is the clinician" });
    act(() => btn.focus());
    await user.keyboard("{Enter}");
    await waitFor(() => expect(mockBackend.getSpeakers(UID, sid).clinician_speaker).toBe("spk_0"));
  });

  it("renders sample lines as text only", async () => {
    const sid = create();
    toAwaiting(sid);
    const evil = '<img src=x onerror="alert(1)"><b>bold</b>';
    server.use(
      http.get("*/v1/sessions/:id/speakers", () =>
        HttpResponse.json({
          speakers: [
            { speaker: "spk_0", turn_count: 1, samples: [evil] },
            { speaker: "spk_1", turn_count: 1, samples: ["fine"] },
          ],
          clinician_speaker: null,
        }),
      ),
    );
    open(sid);
    await cards();
    expect(screen.getByText(evil)).toBeInTheDocument();
    expect(document.querySelector('[data-slot="speaker-gate"] img, [data-slot="speaker-gate"] b')).toBeNull();
  });

  it("shows the API's message when confirming fails", async () => {
    const user = userEvent.setup();
    const sid = create();
    toAwaiting(sid);
    server.use(
      http.post("*/v1/sessions/:id/speakers/confirm", () =>
        HttpResponse.json(
          { schema_version: "0.0.1", error: { code: "invalid_state", message: "Not now.", request_id: "req_9", details: [] } },
          { status: 409 },
        ),
      ),
    );
    open(sid);
    const list = await cards();
    await user.click(within(list[0]).getByRole("button", { name: "This is the clinician" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Speakers" })).toBeInTheDocument();
  });
});

describe("change who the clinician is", () => {
  it("is not offered once the report is ready: the rating is final (FX45)", async () => {
    const sid = reportReady();
    open(sid);
    expect(await screen.findByRole("link", { name: "View report" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change who the clinician is" })).not.toBeInTheDocument();
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(1);
  });

  it("after a transient failure, preselects the current clinician, saves, then re-runs via /retry (never /runs)", async () => {
    const user = userEvent.setup();
    const sid = reportReady("fail-transient");
    const hits: string[] = [];
    const log = ({ request }: { request: Request }) => void hits.push(`${request.method} ${new URL(request.url).pathname}`);
    server.events.on("request:start", log);
    onTestFinished(() => void server.events.removeListener("request:start", log));
    open(sid);
    await user.click(await screen.findByRole("button", { name: "Change who the clinician is" }));
    const list = await cards();
    const radios = list.map((c) => within(c).getByRole("radio", { name: "This is the clinician" }));
    expect(radios[0]).toBeChecked();
    await user.click(radios[1]);
    await user.click(screen.getByRole("button", { name: "Save and try again" }));
    await waitFor(() => expect(mockBackend.listRuns(UID, sid)).toHaveLength(2));
    expect(mockBackend.getSpeakers(UID, sid).clinician_speaker).toBe("spk_1");
    await waitFor(() => expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument());
    expect(hits.filter((h) => /speakers\/confirm|\/retry|\/runs$/.test(h))).toEqual([
      `POST /v1/sessions/${sid}/speakers/confirm`,
      `POST /v1/sessions/${sid}/retry`,
    ]);
  });

  it("is not offered after a permanent failure: only retryable failures re-run (H-5)", async () => {
    const sid = reportReady("fail-code");
    open(sid);
    await screen.findByRole("link", { name: "Start a new session" });
    expect(screen.queryByRole("button", { name: "Change who the clinician is" })).not.toBeInTheDocument();
  });

  it("says the clinician was saved when the re-run itself fails (no half-applied silence)", async () => {
    const user = userEvent.setup();
    const sid = reportReady("fail-transient");
    server.use(
      http.post("*/v1/sessions/:id/retry", () =>
        HttpResponse.json(
          { schema_version: "0.0.1", error: { code: "invalid_state", message: "Not now.", request_id: "req_7", details: [] } },
          { status: 409 },
        ),
      ),
    );
    open(sid);
    await user.click(await screen.findByRole("button", { name: "Change who the clinician is" }));
    const list = await cards();
    await user.click(within(list[1]).getByRole("radio", { name: "This is the clinician" }));
    await user.click(screen.getByRole("button", { name: "Save and try again" }));
    expect(await screen.findByText(/clinician was saved, but the re-run didn't start/i)).toBeInTheDocument();
    expect(mockBackend.getSpeakers(UID, sid).clinician_speaker).toBe("spk_1");
    expect(screen.getByRole("button", { name: "Save and try again" })).toBeEnabled();
  });

  it("can be reopened by keyboard after a failed run", async () => {
    const user = userEvent.setup();
    const sid = reportReady("fail-transient");
    open(sid);
    const link = await screen.findByRole("button", { name: "Change who the clinician is" });
    act(() => link.focus());
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("button", { name: "Save and try again" })).toBeEnabled();
  });

  it("is not offered while the first gate is showing or while running", async () => {
    const sid = create();
    toAwaiting(sid);
    open(sid);
    await cards();
    expect(screen.queryByRole("button", { name: "Change who the clinician is" })).not.toBeInTheDocument();
  });
});
