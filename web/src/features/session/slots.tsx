/**
 * Mount points: the rating card (R4, `features/rating`) and the speaker gate (R4, `features/speakers`). The uploader (R3) lives in
 * `features/upload`.
 */
import { useState } from "react";
import type { SessionStatusDoc } from "../../api/statusListener";
import { SpeakerGate } from "../speakers/SpeakerGate";
import { RatingCard } from "../rating/RatingCard";
export { UploadSlot } from "../upload/UploadSlot";

export interface SlotProps {
  sessionId: string;
  doc: SessionStatusDoc;
}

/** `readOnly`: the rating was submitted, so it is final (FX45). */
export function RatingCardSlot({ sessionId, readOnly = false }: SlotProps & { readOnly?: boolean }) {
  return (
    <div data-slot="rating-card" data-session={sessionId}>
      <RatingCard sessionId={sessionId} readOnly={readOnly} />
    </div>
  );
}

export function SpeakerGateSlot({ sessionId, doc }: SlotProps) {
  const [open, setOpen] = useState(false);
  const rerunnable = doc.state === "failed"; // a ready report is final (FX45)
  return (
    <div data-slot="speaker-gate" data-session={sessionId}>
      {!doc.speaker_confirmed ? (
        <SpeakerGate sessionId={sessionId} mode="first" />
      ) : rerunnable && open ? (
        <SpeakerGate sessionId={sessionId} mode="rerun" onDone={() => setOpen(false)} />
      ) : rerunnable ? (
        <p>
          <button type="button" className="link-button" onClick={() => setOpen(true)}>
            Change who the clinician is
          </button>
        </p>
      ) : null}
    </div>
  );
}
