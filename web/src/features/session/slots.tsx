/**
 * Mount points: the rating card (R4, `features/rating`) and the speaker gate (R4, `features/speakers`). The uploader (R3) lives in
 * `features/upload`.
 */
import type { SessionStatusDoc } from "../../api/statusListener";
import { SpeakerGate } from "../speakers/SpeakerGate";
import { ratingEnabled } from "../../config";
import { RatingCard } from "../rating/RatingCard";
import { SetupFallback } from "../rating/SetupFallback";
export { UploadSlot } from "../upload/UploadSlot";

export interface SlotProps {
  sessionId: string;
  doc: SessionStatusDoc;
}

/** The rating is final once submitted or a run has started. */
export function RatingCardSlot({ sessionId, doc, readOnly = false }: SlotProps & { readOnly?: boolean }) {
  const locked = readOnly || doc.rating_submitted || doc.state === "running" || doc.state === "failed" || doc.state === "report_ready";
  if (!ratingEnabled()) {
    // Flag off (PRD R2/R3): no card; only an unsubmitted, live session gets the goal-only fallback.
    if (doc.rating_submitted || doc.state === "deleting") return null;
    return (
      <div data-slot="rating-fallback" data-session={sessionId}>
        <SetupFallback sessionId={sessionId} />
      </div>
    );
  }
  return (
    <div data-slot="rating-card" data-session={sessionId}>
      <RatingCard sessionId={sessionId} readOnly={locked} />
    </div>
  );
}

export function SpeakerGateSlot({ sessionId, doc }: SlotProps) {
  if (!doc.transcript_ready || doc.speaker_confirmed || doc.state !== "awaiting_input") return null;
  return (
    <div data-slot="speaker-gate" data-session={sessionId}>
      <SpeakerGate sessionId={sessionId} />
    </div>
  );
}
