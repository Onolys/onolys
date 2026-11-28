import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionStatusDoc } from "../../api/statusListener";
import { mockBackend } from "../../mocks/server";
import { renderPage } from "../../test/renderPage";
import { RatingCardSlot, SpeakerGateSlot } from "./slots";

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

afterEach(() => vi.unstubAllEnvs());

describe("speaker gate slot: first confirmation only", () => {
  it("shows the gate for a ready, unconfirmed transcript awaiting input", async () => {
    await mount(awaiting(), failed({ state: "awaiting_input", error_code: null, error_kind: null }));
    expect(await screen.findAllByRole("button", { name: "This is the clinician" })).toHaveLength(2);
  });

  it.each([
    { state: "awaiting_input", speaker_confirmed: true },
    { state: "awaiting_input", transcript_ready: false },
    { state: "failed", error_kind: "transient" },
    { state: "failed", error_kind: "permanent_internal" },
    { state: "running" },
    { state: "report_ready" },
    { state: "transcribing" },
    { state: "deleting" },
  ] satisfies Partial<SessionStatusDoc>[])("hides the gate for %j", async (patch) => {
    await mount(awaiting(), failed(patch));
    expect(document.querySelector('[data-slot="speaker-gate"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "Change who the clinician is" })).not.toBeInTheDocument();
  });
});

describe("rating card slot: locked inputs", () => {
  it.each([
    { state: "awaiting_input", rating_submitted: true },
    { state: "running" },
    { state: "failed" },
    { state: "report_ready" },
  ] satisfies Partial<SessionStatusDoc>[])("locks the card for %j", async (patch) => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    const sid = awaiting();
    await renderPage(<RatingCardSlot sessionId={sid} doc={failed(patch)} />, "/x", { user: USER });
    expect(await screen.findByLabelText("Change goal")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Submit rating" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /No rating/ })).not.toBeInTheDocument();
  });

  it("keeps an unsubmitted awaiting-input card editable", async () => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    const sid = awaiting();
    await renderPage(<RatingCardSlot sessionId={sid} doc={failed({ state: "awaiting_input" })} />, "/x", { user: USER });
    expect(await screen.findByLabelText("Change goal")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Submit rating" })).toBeEnabled();
  });
});

describe.each([undefined, "false"])("rating-disabled slot: locked change goal (flag %s)", (flag) => {
  it.each(["running", "failed", "report_ready", "deleting"] as const)("hides the goal fallback in %s", async (state) => {
    vi.stubEnv("VITE_RATING_ENABLED", flag);
    const sid = awaiting();
    await renderPage(<RatingCardSlot sessionId={sid} doc={failed({ state })} />, "/x", { user: USER });
    expect(document.querySelector('[data-slot="rating-fallback"]')).toBeNull();
    expect(screen.queryByLabelText("Change goal")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
  });

  it("keeps the unsubmitted awaiting-input goal editable", async () => {
    vi.stubEnv("VITE_RATING_ENABLED", flag);
    const sid = awaiting();
    await renderPage(<RatingCardSlot sessionId={sid} doc={failed({ state: "awaiting_input" })} />, "/x", { user: USER });
    expect(await screen.findByLabelText("Change goal")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
  });
});
