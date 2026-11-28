import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { mockBackend, server } from "../../mocks/server";
import { renderApp, uidForEmail } from "../../test/renderApp";

const UID = uidForEmail("rater@clinic.org");
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
/** A session whose first run is finished, so the report is ready or the run failed. */
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
    await open(sid);
    await screen.findByRole("list", { name: "Progress" });
    expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument();
  });

  it("2 speakers: a card each with 3 sample lines and no 'everyone else' note", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
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
    await open(sid);
    expect(await cards()).toHaveLength(3);
    expect(screen.getByText(/everyone else is the client/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "This is the clinician" })).toHaveLength(3);
  });

  it("confirm posts the chosen speaker and the gate goes away", async () => {
    const user = userEvent.setup();
    const sid = create();
    toAwaiting(sid);
    await open(sid);
    const list = await cards();
    await user.click(within(list[1]).getByRole("button", { name: "This is the clinician" }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument());
    expect(mockBackend.getSpeakers(UID, sid).clinician_speaker).toBe("spk_1");
  });

  it("shows friendly numbered labels, never the raw speaker id (C9)", async () => {
    const sid = create();
    toAwaiting(sid);
    await open(sid);
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
    await open(sid);
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
    await open(sid);
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
    await open(sid);
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
    await open(sid);
    const list = await cards();
    await user.click(within(list[0]).getByRole("button", { name: "This is the clinician" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Speakers" })).toBeInTheDocument();
  });
});

describe("clinician choice is final", () => {
  it.each([undefined, "fail-transient", "fail-code"])("does not offer speaker changes after the first run (%s)", async (title) => {
    const sid = reportReady(title);
    await open(sid);
    if (title === "fail-transient") await screen.findByRole("button", { name: /^Retry/ });
    else if (title === "fail-code") await screen.findByRole("link", { name: "Start a new session" });
    else await screen.findByRole("heading", { level: 1, name: "Report" });
    expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change who the clinician is" })).not.toBeInTheDocument();
    expect(mockBackend.listRuns(UID, sid)).toHaveLength(1);
  });
});
