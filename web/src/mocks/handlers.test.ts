import { describe, expect, it, vi } from "vitest";
import { createApiClient, unwrap, type ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import { fakeToken } from "../auth/fake";
import { mockBackend } from "./server";

const BASE = "http://localhost/v1";
const MP3 = { content_type: "audio/mpeg", size_bytes: 5_000_000, filename_ext: "mp3" };

function clientFor(uid: string, getToken?: () => Promise<string | null>) {
  const onSessionExpired = vi.fn();
  const client = createApiClient({
    baseUrl: BASE,
    getToken: getToken ?? (async () => fakeToken(uid)),
    onSessionExpired,
  });
  return { client, onSessionExpired };
}

async function create(client: ApiClient, title?: string) {
  const { session } = unwrap(await client.POST("/sessions", { body: { title } }));
  return session.id;
}

describe("MSW handlers over HTTP (fake auth)", () => {
  it("rejects missing or malformed auth with a public-error-response 401", async () => {
    const { client } = clientFor("u1", async () => null);
    const res = await client.GET("/usage");
    expect(res.response.status).toBe(401);
    expect(res.error).toMatchObject({
      schema_version: "0.0.1",
      status: 401,
      details: [{ code: "unauthenticated" }],
    });
    const bad = clientFor("u1", async () => "not-a-test-token").client;
    expect((await bad.GET("/usage")).response.status).toBe(401);
  });

  it("accepts `Bearer test:<uid>` and isolates users", async () => {
    const a = clientFor("alice").client;
    const b = clientFor("bob").client;
    const sid = await create(a, "mine");
    expect(unwrap(await a.GET("/sessions")).items.map((i) => i.id)).toEqual([sid]);
    expect(unwrap(await b.GET("/sessions")).items).toEqual([]);
    const res = await b.GET("/sessions/{id}", { params: { path: { id: sid } } });
    expect(res.response.status).toBe(404);
    expect(res.error?.details[0].code).toBe("not_found");
  });

  it("runs the whole flow: create, audio, PUT to signed URL, complete, rating, speaker, run, report", async () => {
    const { client } = clientFor("u1");
    const sid = await create(client, "flow");
    const p = { params: { path: { id: sid } } };

    const up = unwrap(await client.POST("/sessions/{id}/audio", { ...p, body: MP3 }));
    expect(up.required_headers["Content-Type"]).toBe("audio/mpeg");

    // signed-URL PUT is handled too; wrong headers are refused like GCS would
    const bad = await fetch(up.upload_url, { method: "PUT", headers: { "Content-Type": "audio/wav" }, body: "x" });
    expect(bad.status).toBe(403);
    const ok = await fetch(up.upload_url, { method: "PUT", headers: up.required_headers, body: "x" });
    expect(ok.status).toBe(200);

    unwrap(await client.POST("/sessions/{id}/audio/complete", p));
    expect(unwrap(await client.GET("/sessions/{id}", p)).status).toBe("validating");

    unwrap(await client.PUT("/sessions/{id}/rating", { ...p, body: { final: false, card: { change_goal: "g" } } }));
    const got = unwrap(await client.GET("/sessions/{id}/rating", p));
    expect(got.draft?.card.change_goal).toBe("g");

    mockBackend.settle(sid); // the worker finishing transcription
    const sp = unwrap(await client.GET("/sessions/{id}/speakers", p));
    expect(sp.speakers).toHaveLength(2);
    unwrap(await client.POST("/sessions/{id}/speakers/confirm", { ...p, body: { clinician_speaker: "spk_0" } }));
    unwrap(await client.PUT("/sessions/{id}/rating", { ...p, body: { final: true, card: { change_goal: "g", globals: { cct: { score: 3 } } } } }));
    expect(unwrap(await client.GET("/sessions/{id}", p))).toMatchObject({ status: "running", step: "paudit" });

    mockBackend.settle(sid);
    const detail = unwrap(await client.GET("/sessions/{id}", p));
    expect(detail).toMatchObject({ status: "report_ready", latest_report_version: 1 });

    const reports = unwrap(await client.GET("/sessions/{id}/reports", p));
    expect(reports.items.map((r) => r.version)).toEqual([1]);
    const report = unwrap(
      await client.GET("/sessions/{id}/reports/{version}", { params: { path: { id: sid, version: 1 } } }),
    );
    expect(report).toMatchObject({ version: 1, report_schema_version: "0.0.1" });
    expect(report.report.scorecard).toHaveLength(14);
    const tr = unwrap(await client.GET("/sessions/{id}/transcript", p));
    expect(tr.turns.length).toBeGreaterThan(5);

    // FX45: the report is final, so a second run and a new final rating are refused
    const again = await client.POST("/sessions/{id}/runs", p);
    expect(again.response.status).toBe(409);
    expect(unwrap(await client.GET("/sessions/{id}/runs", p)).items).toHaveLength(1);

    expect((await client.DELETE("/sessions/{id}", p)).response.status).toBe(204);
    expect((await client.GET("/sessions/{id}", p)).response.status).toBe(404);
  });

  it("maps mock errors to public-error-response bodies with a request id", async () => {
    const { client } = clientFor("u1");
    const sid = await create(client);
    const p = { params: { path: { id: sid } } };

    const tooBig = await client.POST("/sessions/{id}/audio", { ...p, body: { ...MP3, size_bytes: 400 * 1024 * 1024 } });
    expect(tooBig.response.status).toBe(422);
    expect(tooBig.error).toMatchObject({ status: 422, details: [{ code: "audio_too_large" }] });
    expect(tooBig.error?.request_id).toBeTruthy();

    const badState = await client.POST("/sessions/{id}/audio/complete", p);
    expect(badState.response.status).toBe(409);

    const invalid = await client.PUT("/sessions/{id}/rating", {
      ...p,
      body: { final: true, card: { change_goal: "g", notes: "x".repeat(3001) } },
    });
    expect(invalid.response.status).toBe(422);
    expect(invalid.error?.details[0].code).toBe("rating_invalid");

    await expect(Promise.resolve().then(() => unwrap(invalid))).rejects.toBeInstanceOf(ApiError);
  });

  it("returns 429 daily_cap_reached from POST /runs and usage reflects the cap", async () => {
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    const { client } = clientFor("u1");
    const sid = await create(client);
    const p = { params: { path: { id: sid } } };
    mockBackend.settle(sid); // no audio yet: stays created; make it ready by walking the upload
    await client.POST("/sessions/{id}/audio", { ...p, body: MP3 });
    await client.POST("/sessions/{id}/audio/complete", p);
    mockBackend.settle(sid);
    await client.POST("/sessions/{id}/speakers/confirm", { ...p, body: { clinician_speaker: "spk_0" } });
    await client.PUT("/sessions/{id}/rating", { ...p, body: { final: true, card: { change_goal: "g" } } });
    const detail = unwrap(await client.GET("/sessions/{id}", p));
    expect(detail).toMatchObject({ status: "awaiting_input", error: { code: "daily_cap_reached" } });
    const res = await client.POST("/sessions/{id}/runs", p);
    expect(res.response.status).toBe(429);
    expect(res.error?.details[0]).toMatchObject({ code: "daily_cap_reached", period: "day" });
    expect(unwrap(await client.GET("/usage"))).toMatchObject({ eval: { day: { used: 0, cap: 0 } } });
  });

  it("honours Idempotency-Key through the client", async () => {
    const { client } = clientFor("u1");
    const hdr = { "Idempotency-Key": "form-1" };
    const a = unwrap(await client.POST("/sessions", { params: { header: hdr }, body: { title: "t" } }));
    const b = unwrap(await client.POST("/sessions", { params: { header: hdr }, body: { title: "t" } }));
    expect(b.session.id).toBe(a.session.id);
    const c = await client.POST("/sessions", { params: { header: hdr }, body: { title: "other" } });
    expect(c.response.status).toBe(409);
    expect(c.error?.details[0].code).toBe("conflict");
  });

  it("pages GET /sessions with limit and cursor", async () => {
    const { client } = clientFor("u1");
    for (let i = 0; i < 3; i++) await create(client);
    const p1 = unwrap(await client.GET("/sessions", { params: { query: { limit: 2 } } }));
    expect(p1.items).toHaveLength(2);
    const p2 = unwrap(await client.GET("/sessions", { params: { query: { limit: 2, cursor: p1.next_cursor } } }));
    expect(p2.items).toHaveLength(1);
  });
});

describe("MSW interview handlers (SP10)", () => {
  it("lists public scenarios only", async () => {
    const { client } = clientFor("u1");
    const body = unwrap(await client.GET("/scenarios"));
    const { scenarios, voices } = body;
    expect(voices.length).toBeGreaterThan(1);
    expect(body).not.toHaveProperty("default_voice");
    expect(scenarios.length).toBeGreaterThan(0);
    for (const s of scenarios) {
      expect(Object.keys(s).sort()).toEqual(["difficulty", "id", "language", "summary", "title", "voice"]);
      expect(voices).toContain(s.voice);
    }
  });

  it("creates an interview (201, default voice, limits, relay url), reads it and ends it", async () => {
    const { client } = clientFor("u1");
    const { scenarios } = unwrap(await client.GET("/scenarios"));
    const res = await client.POST("/interviews", { body: { scenario_id: scenarios[1].id } });
    expect(res.response.status).toBe(201);
    const iv = unwrap(res);
    expect(iv).toMatchObject({ state: "created", voice: scenarios[1].voice, limits: { max_s: 600, warn_s: 480 } });
    expect(iv.voice_url).toMatch(new RegExp(`^wss://.+/v1/voice/${iv.interview_id}$`));
    expect(unwrap(await client.GET("/interviews/{id}", { params: { path: { id: iv.interview_id } } })).interview_id).toBe(iv.interview_id);
    const ended = unwrap(await client.POST("/interviews/{id}/end", { params: { path: { id: iv.interview_id } }, body: {} }));
    expect(ended.state).toBe("ended");
  });

  it("discard abandons; other users get 404", async () => {
    const { client } = clientFor("u1");
    const iv = unwrap(await client.POST("/interviews", { body: { scenario_id: "sc_anxious_parent", voice: "Puck" } }));
    expect(iv.voice).toBe("Puck");
    const other = clientFor("u2").client;
    const seen = await other.GET("/interviews/{id}", { params: { path: { id: iv.interview_id } } });
    expect(seen.response.status).toBe(404);
    const gone = unwrap(await client.POST("/interviews/{id}/end", { params: { path: { id: iv.interview_id } }, body: { discard: true } }));
    expect(gone.state).toBe("abandoned");
  });

  it("422 invalid_parameters for an unknown scenario or voice", async () => {
    const { client } = clientFor("u1");
    for (const body of [{ scenario_id: "nope" }, { scenario_id: "sc_anxious_parent", voice: "Nobody" }]) {
      const res = await client.POST("/interviews", { body });
      expect(res.response.status).toBe(422);
      expect(res.error?.details[0].code).toBe("invalid_parameters");
    }
    expect(unwrap(await client.GET("/usage")).interview.day.used).toBe(0);
  });

  it("429 interview_cap_reached with the period, counted in GET /usage", async () => {
    mockBackend.configure({ caps: { interview: { day: 1 } } });
    const { client } = clientFor("u1");
    unwrap(await client.POST("/interviews", { body: { scenario_id: "sc_anxious_parent" } }));
    const res = await client.POST("/interviews", { body: { scenario_id: "sc_anxious_parent" } });
    expect(res.response.status).toBe(429);
    expect(res.error?.details[0]).toMatchObject({ code: "interview_cap_reached", period: "day" });
    expect(unwrap(await client.GET("/usage")).interview.day).toMatchObject({ used: 1, cap: 1 });
  });
});
