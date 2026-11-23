/** `/sessions` (PRD R5, D16): the caller's sessions, newest first, with status chips and an empty state. */
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { ratingEnabled } from "../../config";
import { ErrorCard } from "../session/ErrorCard";
import type { components } from "../../api/schema";
import { STATUS_CHIP, sessionsRefetchInterval } from "./chips";

type SessionListItem = components["schemas"]["SessionListItem"];
const PAGE = 20;
const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

export function SessionsList() {
  const client = useApiClient();
  const sessions = useInfiniteQuery({
    queryKey: ["sessions"],
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchInterval: (q: { state: { data?: { pages: { items: SessionListItem[] }[] } } }) =>
      sessionsRefetchInterval(q.state.data?.pages.flatMap((p) => p.items)),
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(await client.GET("/sessions", { params: { query: { limit: PAGE, cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = sessions.data?.pages.flatMap((p) => p.items) ?? [];

  let body;
  if (sessions.isPending) {
    body = <p className="form-note">Loading your sessions…</p>;
  } else if (sessions.isError && items.length === 0) {
    const e = describeError(sessions.error);
    body = (
      <ErrorCard code={e.code} reference={e.requestId}>
        <button type="button" className="link-button" onClick={() => void sessions.refetch()}>
          Try again
        </button>
      </ErrorCard>
    );
  } else if (items.length === 0) {
    body = (
      <div className="empty-state">
        <p>
          {ratingEnabled()
            ? "Onolys rates a recorded session against the MITI and shows you where it agrees with your own rating, line by line."
            : "Onolys codes a recorded session against the MITI, with evidence from your transcript and tips to improve."}
        </p>
        <p>
          <Link to="/new">Start a new session</Link>
        </p>
      </div>
    );
  } else {
    body = (
      <>
        <ul className="session-list">
          {items.map((s) => {
            const chip = STATUS_CHIP[s.status];
            return (
              <li key={s.id} className="session-row">
                <Link to={`/sessions/${s.id}`}>{s.title ?? date(s.created_at)}</Link>{" "}
                {s.interview_id ? (
                  <>
                    <span className="chip">AI interview</span>{" "}
                  </>
                ) : null}
                <span className="chip" data-tone={chip.tone}>
                  {chip.text}
                </span>{" "}
                <span className="form-note">{date(s.created_at)}</span>
                {s.latest_report_version ? (
                  <>
                    {" "}
                    <Link to={`/sessions/${s.id}/reports/${s.latest_report_version}`}>Report v{s.latest_report_version}</Link>
                  </>
                ) : null}
              </li>
            );
          })}
        </ul>
        {sessions.isError ? (
          <ErrorCard code={describeError(sessions.error).code} reference={describeError(sessions.error).requestId}>
            <button type="button" className="link-button" onClick={() => void sessions.refetch()}>
              Try again
            </button>
          </ErrorCard>
        ) : null}
        {sessions.hasNextPage ? (
          <p>
            <button type="button" className="btn btn-secondary" disabled={sessions.isFetchingNextPage} onClick={() => void sessions.fetchNextPage()}>
              Load more
            </button>
          </p>
        ) : null}
      </>
    );
  }
  return body;
}

export function SessionsPage() {
  return (
    <>
      <h1>Sessions</h1>
      <SessionsList />
    </>
  );
}
