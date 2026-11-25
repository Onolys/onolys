/**
 * `/sessions/:id/reports/:version` (PRD R4, D17): the report as a single-column document. The
 * transcript is fetched in parallel; while it loads or fails, the rest of the report still shows
 * and the utterance links / Evidence rows (which need turn numbers) are omitted until it is ready.
 */
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useParams } from "react-router";
import { pageLoadError } from "../../pageLoadError";
import { unwrap } from "../../api/client";
import { describeError, isNotFoundError } from "../../api/errors";
import type { Report } from "../../api/report";
import { Button } from "@onolys/ui";
import { useApiClient } from "../../auth/useApiClient";
import { H1, LINK, LINK_BTN, NOTE, PAGE } from "../../components/classes";
import { Notice } from "../../components/Notice";
import { DeleteSession } from "../session/DeleteSession";
import { ErrorCard } from "../session/ErrorCard";
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
    <div className={PAGE}>
      <h1 className={H1}>Report</h1>
      <p>We couldn't find that report.</p>
      <p>
        <Link to={`/sessions/${id}`} className={LINK}>
          Back to the session
        </Link>
      </p>
    </div>
  );
}

function ReportView({ id, version }: { id: string; version: string }) {
  const valid = /^[1-9]\d*$/.test(version);
  return valid ? <LoadedReport id={id} version={Number(version)} /> : <NotFound id={id} />;
}

function LoadedReport({ id, version }: { id: string; version: number }) {
  const client = useApiClient();
  const view = useQuery({
    queryKey: ["report", id, version],
    throwOnError: pageLoadError,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    queryFn: async () =>
      unwrap(await client.GET("/sessions/{id}/reports/{version}", { params: { path: { id, version } } })),
  });
  // Same query key as the coded-transcript dialog; fetched in parallel so the report renders without waiting for it.
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
      <div className={PAGE}>
        <h1 className={H1}>Report</h1>
        <p className={NOTE}>Loading report…</p>
      </div>
    );
  }
  if (view.isError || !view.data || !report) {
    if (isNotFoundError(view.error)) return <NotFound id={id} />;
    const e = describeError(view.error);
    return (
      <div className={PAGE}>
        <h1 className={H1}>Report</h1>
        <ErrorCard code={e.code} reference={e.requestId}>
          <Button type="button" variant="link" className={LINK_BTN} onClick={() => void view.refetch()}>
            Try again
          </Button>
        </ErrorCard>
      </div>
    );
  }

  const newer = Number.isFinite(major(view.data.report_schema_version)) && major(view.data.report_schema_version) !== SUPPORTED_MAJOR;
  return (
    <>
      <ReportDocument
        report={report}
        reportId={view.data.report_id}
        turns={turns}
        headerSlot={newer ? <Notice role="alert">This report was made by a newer version — refresh</Notice> : undefined}
        footerSlot={<DeleteSession id={id} />}
      />
    </>
  );
}
