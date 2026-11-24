/**
 * Mount points: the rating card (R4, `features/rating`) and the speaker gate (R4, `features/speakers`). The uploader (R3) lives in
 * `features/upload`.
 */
import { Button } from "@onolys/ui";
import { useState } from "react";
import { failureView } from "../../api/errors";
import type { SessionStatusDoc } from "../../api/statusListener";
import { LINK_BTN } from "../../components/classes";
import { SpeakerGate } from "../speakers/SpeakerGate";
import { ratingEnabled } from "../../config";
import { RatingCard } from "../rating/RatingCard";
import { SetupFallback } from "../rating/SetupFallback";
export { UploadSlot } from "../upload/UploadSlot";

export interface SlotProps {
  sessionId: string;
  doc: SessionStatusDoc;
}

/** `readOnly`: the rating was submitted, so it is final (FX45). */
export function RatingCardSlot({ sessionId, doc, readOnly = false }: SlotProps & { readOnly?: boolean }) {
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
      <RatingCard sessionId={sessionId} readOnly={readOnly} />
    </div>
  );
}

export function SpeakerGateSlot({ sessionId, doc }: SlotProps) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  // Only a retryable failure re-runs (via /retry); a ready report is final (FX45) and a permanent failure needs a new session.
  const failed = doc.state === "failed";
  const rerunnable = failed && failureView(doc).action === "retry";
  // A failed session whose speaker was never confirmed opens the rerun gate (confirm, then /retry): "first" would only confirm and leave it failed.
  const showRerun = rerunnable && (open || (!doc.speaker_confirmed && !dismissed));
  return (
    <div data-slot="speaker-gate" data-session={sessionId}>
      {!doc.speaker_confirmed && !failed ? (
        <SpeakerGate sessionId={sessionId} mode="first" />
      ) : showRerun ? (
        <SpeakerGate
          sessionId={sessionId}
          mode="rerun"
          onDone={() => {
            setOpen(false);
            setDismissed(true);
          }}
        />
      ) : rerunnable ? (
        <div>
          <Button type="button" variant="link" className={LINK_BTN} onClick={() => setOpen(true)}>
            Change who the clinician is
          </Button>
        </div>
      ) : null}
    </div>
  );
}
