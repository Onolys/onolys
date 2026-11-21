/** `/` (PRD R5, D16): the caller's sessions, newest first, with status chips, usage and an empty state. */
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { unwrap } from "../../api/client";
import { describeError, messageForCode } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { interviewCapText } from "../interview/capText";
import { ErrorCard } from "../session/ErrorCard";
import { UsageLeft } from "../usage/UsageLeft";
import { blockingPeriod, evalCapCode, formatBlockingReset } from "../usage/usage";
import { useUsage } from "../usage/useUsage";
import type { components } from "../../api/schema";
import { STATUS_CHIP, sessionsRefetchInterval } from "./chips";

type SessionListItem = components["schemas"]["SessionListItem"];
const PAGE = 20;
const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

export function Dashboard() {
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
  const usage = useUsage();
  const blocking = blockingPeriod(usage.data, "eval");
  const interviewBlocking = blockingPeriod(usage.data, "interview");

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
        <p>Onolys rates a recorded session against the MITI and shows you where it agrees with your own rating, line by line.</p>
        <p>
          <Link to="/sample-report">See a sample report</Link>
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

  return (
    <>
      <h1>Sessions</h1>
      <div className="landing-cards">
        <section className="landing-card" aria-labelledby="card-interview">
          <h2 id="card-interview">Practise with an AI client</h2>
          <p className="form-note">
            A 10-minute role-play, then rated like any recording.
            {usage.data ? (
              <>
                {" "}
                <UsageLeft kind="interview" period="day" />, <UsageLeft kind="interview" period="month" />
              </>
            ) : null}
          </p>
          {interviewBlocking ? (
            <>
              <button type="button" className="btn btn-primary" disabled>
                Start AI Interview
              </button>
              <p className="notice">{interviewCapText(interviewBlocking)}</p>
            </>
          ) : (
            <Link className="btn btn-primary" to="/interviews/new">
              Start AI Interview
            </Link>
          )}
        </section>
        <section className="landing-card" aria-labelledby="card-upload">
          <h2 id="card-upload">Rate a recording</h2>
          <p className="form-note">
            Bring a session you recorded.
            {usage.data ? (
              <>
                {" "}
                <UsageLeft kind="eval" period="day" />, <UsageLeft kind="eval" period="month" />
              </>
            ) : null}
          </p>
          <Link className="btn btn-primary" to="/sessions/new">
            New session
          </Link>
          {blocking ? (
            <p className="notice">{messageForCode(evalCapCode(blocking), { resetsAt: formatBlockingReset(blocking) })}</p>
          ) : null}
        </section>
      </div>
      {body}
    </>
  );
}
