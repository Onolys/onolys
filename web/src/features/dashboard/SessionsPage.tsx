/** `/sessions` (PRD R5, D16): the caller's sessions, newest first, with status chips and an empty state. */
import { Badge, Button, Card, CardContent, Skeleton } from "@onolys/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { H1, LINK, LINK_BTN, NOTE, PAGE as PAGE_STACK } from "../../components/classes";
import { StatusChip } from "../../components/StatusChip";
import { ratingEnabled } from "../../config";
import { ErrorCard } from "../session/ErrorCard";
import type { components } from "../../api/schema";
import { formatDate } from "../../lib/format";
import { chipFor, sessionsRefetchInterval } from "./chips";

type SessionListItem = components["schemas"]["SessionListItem"];
const PAGE = 20;
const date = formatDate;

export function SessionsPage() {
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
    body = (
      <div aria-busy="true" className="grid gap-3">
        <p className={NOTE}>Loading your sessions…</p>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  } else if (sessions.isError && items.length === 0) {
    const e = describeError(sessions.error);
    body = (
      <ErrorCard code={e.code} reference={e.requestId}>
        <Button type="button" variant="link" className={LINK_BTN} onClick={() => void sessions.refetch()}>
          Try again
        </Button>
      </ErrorCard>
    );
  } else if (items.length === 0) {
    body = (
      <Card>
        <CardContent className="grid justify-items-start gap-4">
          <p>
            {ratingEnabled()
              ? "Onolys rates a recorded session against the MITI and shows you where it agrees with your own rating, line by line."
              : "Onolys codes a recorded session against the MITI, with evidence from your transcript and tips to improve."}
          </p>
          <Button asChild>
            <Link to="/new">Start a new session</Link>
          </Button>
        </CardContent>
      </Card>
    );
  } else {
    body = (
      <>
        <Card className="py-0">
          <ul className="m-0 grid list-none p-0">
            {items.map((s) => {
              const chip = chipFor(s.status);
              return (
                <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-4 py-3 last:border-b-0">
                  <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
                    <Link to={s.latest_report_version != null ? `/sessions/${s.id}/reports/${s.latest_report_version}` : `/sessions/${s.id}`} className={`${LINK} flex min-h-11 min-w-0 items-center break-words [overflow-wrap:anywhere]`}>
                      {s.title ?? date(s.created_at)}
                    </Link>
                    {s.interview_id ? <Badge variant="outline">AI interview</Badge> : null}
                    <StatusChip tone={chip.tone}>{chip.text}</StatusChip>
                  </div>
                  <time dateTime={s.created_at} className={`${NOTE} ml-auto w-full shrink-0 text-right sm:w-auto`}>{date(s.created_at)}</time>
                </li>
              );
            })}
          </ul>
        </Card>
        {sessions.isError ? (
          <ErrorCard code={describeError(sessions.error).code} reference={describeError(sessions.error).requestId}>
            <Button type="button" variant="link" className={LINK_BTN} onClick={() => void sessions.refetch()}>
              Try again
            </Button>
          </ErrorCard>
        ) : null}
        {sessions.hasNextPage ? (
          <div>
            <Button type="button" variant="outline" disabled={sessions.isFetchingNextPage} onClick={() => void sessions.fetchNextPage()}>
              Load more
            </Button>
          </div>
        ) : null}
      </>
    );
  }
  return (
    <div className={PAGE_STACK}>
      <h1 className={H1}>Sessions</h1>
      {body}
    </div>
  );
}
