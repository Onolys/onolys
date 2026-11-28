import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockBackend, server } from "../../mocks/server";
import { here } from "../../test/renderApp";
import { renderPage } from "../../test/renderPage";
import { DASHBOARD_POLL_MS, sessionsRefetchInterval } from "./chips";
import { SessionsPage } from "./SessionsPage";

const render = (opts: Parameters<typeof renderPage>[2]) => renderPage(<SessionsPage />, "/sessions", opts);
const UID = "u_rater_clinic_org";
const USER = { email: "rater@clinic.org", verified: true };

const create = (title?: string) => mockBackend.createSession(UID, { title }).session.id;
const main = () => within(screen.getByRole("main"));
const rowOf = (name: RegExp | string) => main().getByRole("link", { name }).closest("li") as HTMLElement;

const item = (id: string, status: string, extra: object = {}) => ({
  id,
  title: `Session ${id}`,
  status,
  created_at: "2026-11-18T10:00:00.000Z",
  latest_report_version: null,
  error_code: null,
  ...extra,
});

describe("sessions page: list", () => {
  it("shows a status chip for every state, each row linking to the session", async () => {
    const cases: [string, string][] = [
      ["created", "Uploading"],
      ["uploading", "Uploading"],
      ["upload_incomplete", "Upload incomplete"],
      ["validating", "Checking audio"],
      ["transcribing", "Transcribing"],
      ["awaiting_input", "Needs your input"],
      ["running", "Rating"],
      ["report_ready", "Report ready"],
      ["failed", "Failed"],
      ["deleting", "Deleting"],
    ];
    server.use(
      http.get("*/v1/sessions", () =>
        HttpResponse.json({ items: cases.map(([s], i) => item(`s${i}`, s, s === "report_ready" ? { latest_report_version: 2 } : {})) }),
      ),
    );
    await render({ user: USER });
    for (const [i, [, label]] of cases.entries()) {
      const li = await waitFor(() => rowOf(`Session s${i}`));
      expect(within(li).getByText(label)).toBeInTheDocument();
      expect(within(li).getByRole("link", { name: `Session s${i}` })).toHaveAttribute("href", i === 7 ? `/sessions/s${i}/reports/2` : `/sessions/s${i}`);
    }
  });

  it("links completed titles straight to the report with one link per row", async () => {
    server.use(
      http.get("*/v1/sessions", () =>
        HttpResponse.json({
          items: [
            item("run1", "running"),
            item("bad1", "failed", { error_code: "internal_error" }),
            item("ok1", "report_ready", { latest_report_version: 3 }),
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    const { router } = await render({ user: USER });
    expect(await main().findByRole("link", { name: "Session run1" })).toHaveAttribute("href", "/sessions/run1");
    expect(main().getByRole("link", { name: "Session bad1" })).toHaveAttribute("href", "/sessions/bad1");
    expect(within(rowOf("Session run1")).queryByRole("link", { name: /Report v/ })).toBeNull();
    expect(main().getByRole("link", { name: "Session ok1" })).toHaveAttribute("href", "/sessions/ok1/reports/3");
    const completedRow = rowOf("Session ok1");
    expect(within(completedRow).getAllByRole("link")).toHaveLength(1);
    expect(within(completedRow).queryByRole("link", { name: /Report v/ })).toBeNull();
    expect(completedRow.lastElementChild?.tagName).toBe("TIME");
    expect(completedRow.lastElementChild).toHaveAttribute("dateTime", "2026-11-18T10:00:00.000Z");
    const rep = within(completedRow).getByRole("link", { name: "Session ok1" });
    await user.click(rep);
    expect(here(router)).toBe("/sessions/ok1/reports/3");
  });

  it("uses the date when a session has no title", async () => {
    server.use(http.get("*/v1/sessions", () => HttpResponse.json({ items: [item("x1", "failed", { title: null })] })));
    await render({ user: USER });
    const link = await main().findByRole("link", { name: /Nov 18, 2026/ });
    expect(link).toHaveAttribute("href", "/sessions/x1");
  });

  it("pages with Load more until next_cursor runs out", async () => {
    const user = userEvent.setup();
    for (let i = 1; i <= 23; i++) create(`S${String(i).padStart(2, "0")}`);
    const calls: string[] = [];
    server.events.on("request:start", ({ request }) => {
      const u = new URL(request.url);
      if (u.pathname.endsWith("/v1/sessions")) calls.push(u.search);
    });
    await render({ user: USER });
    await main().findByRole("link", { name: "S23" });
    expect(main().getAllByRole("listitem")).toHaveLength(20);
    expect(main().queryByRole("link", { name: "S03" })).toBeNull();
    await user.click(main().getByRole("button", { name: "Load more" }));
    await main().findByRole("link", { name: "S01" });
    expect(main().getAllByRole("listitem")).toHaveLength(23);
    expect(main().queryByRole("button", { name: "Load more" })).toBeNull();
    expect(calls[1]).toContain("cursor=20");
    server.events.removeAllListeners();
  });

  it("keeps a request error local with a working Try again", async () => {
    let fail = true;
    server.use(
      http.get("*/v1/sessions", () =>
        fail
          ? HttpResponse.json(
              { schema_version: "0.0.1", status: 400, message: "x", details: [{ code: "invalid_parameters", message: "x" }], request_id: "r" },
              { status: 400 },
            )
          : HttpResponse.json({ items: [item("z", "running")] }),
      ),
    );
    const user = userEvent.setup();
    await render({ user: USER });
    const btn = await main().findByRole("button", { name: "Try again" });
    fail = false;
    await user.click(btn);
    expect(await main().findByRole("link", { name: "Session z" })).toBeInTheDocument();
  });
});

describe("sessions page: heading", () => {
  it("has the Sessions h1 and no landing cards", async () => {
    await render({ user: USER });
    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
  });
});

describe("sessions page: empty state", () => {
  it("explains Onolys in one line and links to /new, with no sample link", async () => {
    const user = userEvent.setup();
    const { router } = await render({ user: USER });
    expect(await main().findByText(/Onolys .*MITI/i)).toBeInTheDocument();
    expect(main().getByText(/evidence from your transcript and tips to improve/i)).toBeInTheDocument();
    expect(main().queryByText(/your own rating/i)).toBeNull();
    expect(main().queryByRole("link", { name: /sample/i })).toBeNull();
    const link = main().getByRole("link", { name: "Start a new session" });
    expect(link).toHaveAttribute("href", "/new");
    await user.click(link);
    expect(here(router)).toBe("/new");
  });
});

describe("sessions page: freshness", () => {
  it("polls every 10 s only while a session is in progress", () => {
    expect(sessionsRefetchInterval([{ status: "report_ready" }, { status: "running" }])).toBe(DASHBOARD_POLL_MS);
    expect(DASHBOARD_POLL_MS).toBe(10_000);
    expect(sessionsRefetchInterval([{ status: "report_ready" }, { status: "failed" }, { status: "awaiting_input" }])).toBe(false);
    expect(sessionsRefetchInterval(undefined)).toBe(false);
  });

  it("keeps the loaded list and shows an inline error when Load more fails", async () => {
    let calls = 0;
    server.use(
      http.get("*/v1/sessions", () => {
        calls++;
        if (calls === 1) return HttpResponse.json({ items: [item("a1", "report_ready")], next_cursor: "c2" });
        return HttpResponse.json({ error: { code: "internal", message: "x" } }, { status: 500 });
      }),
    );
    await render({ user: USER });
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(main().getByRole("link", { name: "Session a1" })).toBeInTheDocument();
  });
});

describe("sessions page: empty state, rating flag on", () => {
  afterEach(() => vi.unstubAllEnvs());
  it("keeps the comparison sentence", async () => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    await render({ user: USER });
    expect(await main().findByText(/agrees with your own rating/i)).toBeInTheDocument();
  });
});

describe("sessions page: unknown status (C17)", () => {
  it("renders a neutral chip instead of crashing the dashboard", async () => {
    server.use(http.get("*/v1/sessions", () => HttpResponse.json({ items: [item("s0", "brand_new_state"), item("s1", "report_ready", { latest_report_version: 1 })] })));
    await render({ user: USER });
    const li = await waitFor(() => rowOf("Session s0"));
    expect(within(li).getByText("Status unavailable")).toBeInTheDocument();
    expect(within(rowOf("Session s1")).getByText("Report ready")).toBeInTheDocument();
  });
});
