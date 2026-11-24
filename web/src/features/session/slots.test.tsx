import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, onTestFinished } from "vitest";
import type { SessionStatusDoc } from "../../api/statusListener";
import { mockBackend, server } from "../../mocks/server";
import { renderPage } from "../../test/renderPage";
import { SpeakerGateSlot } from "./slots";

const UID = "u_rater_clinic_org";
const USER = { email: "rater@clinic.org", verified: true };

function awaiting() {
  const sid = mockBackend.createSession(UID, {}).session.id;
  mockBackend.requestAudio(UID, sid, { content_type: "audio/mpeg", size_bytes: 10, filename_ext: "mp3" });
  mockBackend.completeAudio(UID, sid);
  mockBackend.settle(sid);
  return sid;
}
const failed = (extra: Partial<SessionStatusDoc>): SessionStatusDoc => ({
  uid: UID,
  state: "failed",
  step: null,
  progress: 40,
  error_code: "transcription_failed",
  error_kind: "transient",
  retries_left: 1,
  latest_report_version: null,
  updated_at: "2026-11-24T10:00:00.000Z",
  transcript_ready: true,
  speaker_confirmed: false,
  rating_submitted: false,
  has_rating: false,
  ...extra,
});
const mount = (sid: string, doc: SessionStatusDoc) => renderPage(<SpeakerGateSlot sessionId={sid} doc={doc} />, "/x", { user: USER });

describe("speaker gate slot: failed session that never confirmed a speaker (C-gate)", () => {
  it("retryable failure: confirming saves the clinician and then re-runs via /retry", async () => {
    const user = userEvent.setup();
    const sid = awaiting();
    const hits: string[] = [];
    const log = ({ request }: { request: Request }) => void hits.push(`${request.method} ${new URL(request.url).pathname}`);
    server.events.on("request:start", log);
    onTestFinished(() => void server.events.removeListener("request:start", log));
    mount(sid, failed({}));
    const list = await screen.findByRole("list", { name: "Speakers" });
    const cards = within(list).getAllByRole("listitem").filter((li) => li.parentElement === list);
    await user.click(within(cards[1]!).getByRole("radio", { name: "This is the clinician" }));
    await user.click(screen.getByRole("button", { name: "Save and try again" }));
    await waitFor(() => expect(hits.filter((h) => /speakers\/confirm|\/retry|\/runs$/.test(h))).toEqual([
      `POST /v1/sessions/${sid}/speakers/confirm`,
      `POST /v1/sessions/${sid}/retry`,
    ]));
  });

  it("permanent failure: the gate is not offered", async () => {
    const sid = awaiting();
    mount(sid, failed({ error_kind: "permanent_internal" }));
    await waitFor(() => expect(screen.getByRole("main")).toBeInTheDocument());
    expect(screen.queryByRole("list", { name: "Speakers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /this is the clinician/i })).not.toBeInTheDocument();
  });

  it("a non-failed session still gets the first-mode gate (confirm only)", async () => {
    const sid = awaiting();
    mount(sid, failed({ state: "awaiting_input", error_code: null, error_kind: null }));
    expect(await screen.findAllByRole("button", { name: "This is the clinician" })).toHaveLength(2);
  });
});
