import type { components } from "../../api/schema";

type State = components["schemas"]["SessionListItem"]["status"];

export interface StatusChip {
  text: string;
  tone: "progress" | "wait" | "done" | "failed" | "neutral" | "muted";
}

/** Dashboard status chip (PRD R5): text says it, tone only adds colour. */
export const STATUS_CHIP: Record<State, StatusChip> = {
  created: { text: "Uploading", tone: "progress" },
  uploading: { text: "Uploading", tone: "progress" },
  upload_incomplete: { text: "Upload incomplete", tone: "wait" },
  validating: { text: "Checking audio", tone: "progress" },
  transcribing: { text: "Transcribing", tone: "progress" },
  awaiting_input: { text: "Needs your input", tone: "wait" },
  running: { text: "Rating", tone: "progress" },
  report_ready: { text: "Report ready", tone: "done" },
  failed: { text: "Failed", tone: "failed" },
  cancelled: { text: "Cancelled", tone: "muted" },
  deleting: { text: "Deleting", tone: "progress" },
};

/** A status this build does not know (a newer server) reads neutral instead of crashing the list. */
const UNKNOWN_CHIP: StatusChip = { text: "Status unavailable", tone: "neutral" };
export const chipFor = (status: State): StatusChip => STATUS_CHIP[status] ?? UNKNOWN_CHIP;

/** Dashboard auto-refresh (D8): poll while any listed session is still moving. */
export const DASHBOARD_POLL_MS = 10_000;
export function sessionsRefetchInterval(items: { status: State }[] | undefined): number | false {
  return items?.some((s) => chipFor(s.status).tone === "progress") ? DASHBOARD_POLL_MS : false;
}
