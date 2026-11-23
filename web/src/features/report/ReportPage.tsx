/**
 * `/sessions/:id/reports/:version` (PRD R4, D17): the report as a single-column document. The
 * transcript is fetched in parallel; while it loads or fails, the rest of the report still shows
 * and the utterance links / Evidence rows (which need turn numbers) are omitted until it is ready.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { unwrap } from "../../api/client";
import { describeError, isNotFoundError } from "../../api/errors";
import type { Report } from "../../api/report";
import { useApiClient } from "../../auth/useApiClient";
import { ErrorCard } from "../session/ErrorCard";
import { CodedTranscriptProvider } from "./CodedTranscriptDialog";
import { ReportView as ReportDocument, type TurnsState } from "./ReportView";

/** Major version of the report schema this UI understands. */
const SUPPORTED_MAJOR = 0;
const major = (v: string | undefined) => Number.parseInt((v ?? "").split(".")[0] ?? "", 10);

export function ReportPage() {
  const { id = "", version = "" } = useParams();
  return <ReportView key={`${id}/${version}`} id={id} version={version} />;
}

function NotFound({ id }: { id: string }) {
  return (
    <>
      <h1>Report</h1>
      <p>We couldn't find that report.</p>
      <p>
        <Link to={`/sessions/${id}`}>Back to the session</Link>
      </p>
    </>
  );
}

function ReportView({ id, version }: { id: string; version: string }) {
  const valid = /^[1-9]\d*$/.test(version);
  return valid ? <LoadedReport id={id} version={Number(version)} /> : <NotFound id={id} />;
}

function LoadedReport({ id, version }: { id: string; version: number }) {
  const client = useApiClient();
  const navigate = useNavigate();

  const view = useQuery({
    queryKey: ["report", id, version],
    staleTime: 0,
    gcTime: 0,
    retry: false,
    queryFn: async () =>
      unwrap(await client.GET("/sessions/{id}/reports/{version}", { params: { path: { id, version } } })),
  });
  const versions = useQuery({
    queryKey: ["reports", id],
    staleTime: 0,
    gcTime: 0,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}/reports", { params: { path: { id } } })),
  });
  // Same query as TranscriptPanel; fetched in parallel so the report renders without waiting for it.
  const transcript = useQuery({
    queryKey: ["transcript", id],
    staleTime: 0,
    gcTime: 0,
    retry: false,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}/transcript", { params: { path: { id } } })),
  });
  const report = view.data?.report as Report | undefined;

  const turns: TurnsState = useMemo(
    () =>
      transcript.isError
        ? { status: "error", retry: () => void transcript.refetch() }
        : transcript.data
          ? { status: "ready", turns: transcript.data.turns }
          : { status: "loading" },
    [transcript],
  );

  if (view.isPending) {
    return (
      <>
        <h1>Report</h1>
        <p className="form-note">Loading report…</p>
      </>
    );
  }
  if (view.isError || !view.data || !report) {
    if (isNotFoundError(view.error)) return <NotFound id={id} />;
    const e = describeError(view.error);
    return (
      <>
        <h1>Report</h1>
        <ErrorCard code={e.code} reference={e.requestId}>
          <button type="button" className="link-button" onClick={() => void view.refetch()}>
            Try again
          </button>
        </ErrorCard>
      </>
    );
  }

  const newer = Number.isFinite(major(view.data.report_schema_version)) && major(view.data.report_schema_version) !== SUPPORTED_MAJOR;
  const h = report.header;
  const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  const details = [
    h.stt ? [h.stt.provider, h.stt.model].filter(Boolean).join(" ") : null,
    h.preset,
    h.code_version,
  ].filter(Boolean);

  const headerSlot = (
    <>
      {newer ? (
        <p className="notice" role="alert">
          This report was made by a newer version — refresh
        </p>
      ) : null}
      <p className="form-note">Run details: {details.join(" · ") || "not recorded"}</p>
      <div className="report-actions">
        <label>
          Version{" "}
          <select
            value={String(version)}
            onChange={(e) => void navigate(`/sessions/${id}/reports/${e.target.value}`)}
          >
            {(versions.data?.items ?? [{ version, created_at: view.data.created_at }]).map((v) => (
              <option key={v.version} value={String(v.version)}>
                v{v.version} · {date(v.created_at)}
              </option>
            ))}
          </select>
        </label>
      </div>
    </>
  );

  return (
    <CodedTranscriptProvider report={report} turns={turns}>
      <ReportDocument report={report} turns={turns} headerSlot={headerSlot} />
    </CodedTranscriptProvider>
  );
}
