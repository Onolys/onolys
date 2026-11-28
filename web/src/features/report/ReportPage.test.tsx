import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { drinkingSampleReport, drinkingSampleTurns } from "../../mocks/fixtures/sample";
import { mockBackend, server } from "../../mocks/server";
import { here, renderApp } from "../../test/renderApp";

const UID = "u_rater_clinic_org";
const USER = { email: "rater@clinic.org", verified: true };
const SCORED = { change_goal: "Walk more in the evenings", globals: { cct: { score: 3 } } };

/** A session at report_ready with v1 made from `rating`. */
function reported(rating: object, title?: string): string {
  const sid = mockBackend.createSession(UID, { title }).session.id;
  mockBackend.requestAudio(UID, sid, { content_type: "audio/mpeg", size_bytes: 10, filename_ext: "mp3" });
  mockBackend.completeAudio(UID, sid);
  mockBackend.settle(sid);
  mockBackend.confirmSpeaker(UID, sid, "spk_0");
  mockBackend.putRating(UID, sid, rating as never);
  mockBackend.settle(sid);
  return sid;
}

const open = (sid: string, version: string | number = 1) =>
  renderApp(`/sessions/${sid}/reports/${version}`, { user: USER });

/** Serve a hand-made report for any version (the API wraps the report in an envelope). */
function serve(report: unknown, schemaVersion = "0.0.1") {
  server.use(
    http.get("*/v1/sessions/:id/reports/:version", () =>
      HttpResponse.json({
        version: 1,
        report_id: "rep_x",
        run_id: "run_x",
        created_at: "2026-11-20T09:30:00.000Z",
        report_schema_version: schemaVersion,
        report,
      }),
    ),
  );
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const clone = () => structuredClone(drinkingSampleReport) as unknown as Record<string, any>;

/** Serve the transcript the report was made from (ids t1..t54 match the fixture report). */
function serveTranscript() {
  server.use(http.get("*/v1/sessions/:id/transcript", () => HttpResponse.json({ turns: drinkingSampleTurns })));
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("report page", () => {
  it("shows the report ID before the goal without run details or version selection", async () => {
    serve(clone());
    serveTranscript();
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    expect(await screen.findByRole("heading", { level: 1, name: "Report" })).toBeInTheDocument();
    expect(await screen.findByText(/Cut down on drinking/)).toBeInTheDocument();
    expect(screen.getAllByText(/MITI 4\.2\.1/).length).toBeGreaterThan(0);
    expect(screen.getByText("rep_x")).toBeInTheDocument();
    expect(screen.getByText("Report ID:").parentElement?.nextElementSibling).toHaveTextContent("Change goal:");
    expect(screen.queryByText(/Run details/)).toBeNull();
    expect(screen.queryByLabelText("Version")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "At a glance",
      "Feedback: ideas to try",
      "Behaviour counts",
      "Coded transcript",
      "Method & limits",
    ]);
    expect(screen.queryByRole("heading", { name: /Scorecard|disagrees|Your reasons/i })).toBeNull();
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("button", { name: /run again|edit my rating|submit/i })).toBeNull();
    expect(screen.queryByText(/^Sample$/)).toBeNull();
  });

  it("once the transcript loads, utterance links appear and the button opens the coded transcript", async () => {
    serve(clone());
    serveTranscript();
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    const btn = await screen.findByRole("button", { name: "Open coded transcript" });
    expect(screen.getAllByRole("button", { name: /^Open utterance \d+$/ }).length).toBeGreaterThan(0);
    await userEvent.click(btn);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("table")).toBeInTheDocument();
  });

  it("a transcript 500 keeps every other section and offers Try again, which recovers", async () => {
    serve(clone());
    let fail = true;
    server.use(
      http.get("*/v1/sessions/:id/transcript", () =>
        fail ? HttpResponse.json({ status: 500 }, { status: 500 }) : HttpResponse.json({ turns: drinkingSampleTurns }),
      ),
    );
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    const retry = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByRole("heading", { name: "At a glance" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Feedback/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Behaviour counts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Method & limits" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Open utterance/ })).toBeNull();
    fail = false;
    await userEvent.click(retry);
    expect(await screen.findByRole("button", { name: "Open coded transcript" })).toBeEnabled();
    expect(screen.getAllByRole("button", { name: /^Open utterance \d+$/ }).length).toBeGreaterThan(0);
  });

  it("renders the report before the transcript arrives", async () => {
    serve(clone());
    server.use(http.get("*/v1/sessions/:id/transcript", () => new Promise(() => {})));
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    expect(await screen.findByRole("heading", { name: "At a glance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Loading transcript…" })).toBeDisabled();
  });
});

describe("report page, deletion", () => {
  it("requires confirmation, allows cancellation, then deletes and returns to sessions", async () => {
    const sid = reported({ final: true, card: SCORED });
    const { router } = await open(sid);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete session" }));
    expect(screen.getByRole("alertdialog", { name: "Delete this session?" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(here(router)).toBe(`/sessions/${sid}/reports/1`);
    await user.click(screen.getByRole("button", { name: "Delete session" }));
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(here(router)).toBe("/sessions"));
  });

  it("keeps deletion errors in the confirmation dialog and permits retry", async () => {
    const sid = reported({ final: true, card: SCORED });
    let attempts = 0;
    server.use(http.delete("*/v1/sessions/:id", () => {
      attempts += 1;
      return HttpResponse.json({ status: 503, details: [{ code: "upstream_unavailable", message: "unavailable" }], request_id: "req_delete" }, { status: 503 });
    }));
    const { router } = await open(sid);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Delete session" }));
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));
    const dialog = screen.getByRole("alertdialog", { name: "Delete this session?" });
    expect(await within(dialog).findByText(/req_delete/)).toBeInTheDocument();
    expect(here(router)).toBe(`/sessions/${sid}/reports/1`);
    await user.click(within(dialog).getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(attempts).toBe(2));
  });
});

describe("report page, tolerance", () => {
  it("warns on a newer major schema_version", async () => {
    serve(clone(), "1.2.0");
    serveTranscript();
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    expect(await screen.findByText(/This report was made by a newer version/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "At a glance" })).toBeInTheDocument();
  });

  it("no mismatch notice for the same major", async () => {
    serve(clone(), "0.9.0");
    serveTranscript();
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    await screen.findByRole("heading", { name: "At a glance" });
    expect(screen.queryByText(/newer version/)).toBeNull();
  });

  it("N>1: behaviour table shows the mean across runs, not run 1 (W28)", async () => {
    const r = clone();
    r.header.n_runs = 3;
    const b = r.behaviours.find((x: { item_id: string }) => x.item_id === "cr")!;
    b.onolys_count = { mean: 7, min: 2, max: 12, values: [2, 7, 12] };
    serve(r);
    serveTranscript();
    const sid = reported({ final: true, card: SCORED });
    await open(sid);
    const table = within(await screen.findByRole("table", { name: "Behaviour counts" }));
    expect(within(table.getByRole("row", { name: /Complex reflection/i })).getByText("7")).toBeInTheDocument();
  });

  it("a malformed session id (422 invalid_parameters) shows the same not-found page as 404 (E21)", async () => {
    server.use(
      http.get("*/v1/sessions/:id/reports/:version", () =>
        HttpResponse.json(
          { schema_version: "0.0.1", status: 422, message: "x", details: [{ code: "invalid_parameters", message: "x" }], request_id: "req_422" },
          { status: 422 },
        ),
      ),
    );
    await open("not-hex");
    expect(await screen.findByText("We couldn't find that report.")).toBeInTheDocument();
  });

  it("a version that is not a whole number shows a not-found message", async () => {
    const sid = reported({ final: true, card: SCORED });
    await open(sid, "abc");
    expect(await screen.findByText(/couldn't find that report/i)).toBeInTheDocument();
  });

  it("an unknown version shows a not-found message with a link back to the session", async () => {
    const sid = reported({ final: true, card: SCORED });
    await open(sid, 9);
    expect(await screen.findByText(/couldn't find that report/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the session" })).toHaveAttribute("href", `/sessions/${sid}`);
  });
});
