/**
 * Session setup on the upload screen (PRD R3, D3): one required "Change goal" field, shown only
 * while the rating UI is off. Reuses the card helpers for validation and the PUT payload; the
 * rating card itself is untouched. The coded span is never sent (the engine picks it, D3d).
 */
import { Label, Textarea } from "@onolys/ui";
import { useId } from "react";
import { unwrap } from "../../api/client";
import { ApiError } from "../../api/errors";
import type { ApiClient } from "../../api/client";
import { LIMITS } from "../../protocol/miti-items";
import { buildCard, emptyForm, localIssues, softCount, type Card } from "./card";

const formFor = (goal: string) => ({ ...emptyForm(), changeGoal: goal });

/** Local blockers for the goal (blank). Empty object when fine. */
export const goalIssues = (goal: string) => localIssues(formFor(goal), { noRating: true });

/** Final no-rating card carrying only the goal. */
export const goalCard = (goal: string): Card => buildCard(formFor(goal), { noRating: true });

/**
 * Save the goal as the final no-rating card. 409 `rating_final` (already final) counts as done;
 * every other error (e.g. 422 `rating_invalid`) is rethrown for the caller.
 */
export async function saveGoal(client: ApiClient, sessionId: string, goal: string): Promise<void> {
  try {
    unwrap(
      await client.PUT("/sessions/{id}/rating", {
        params: { path: { id: sessionId } },
        body: { final: true, no_rating: true, card: goalCard(goal) },
      }),
    );
  } catch (e) {
    if (!(e instanceof ApiError && e.code === "rating_final")) throw e;
  }
}

export interface SetupFieldsProps {
  goal: string;
  onGoal: (v: string) => void;
  /** Locked once the goal is stored for the session. */
  disabled?: boolean;
  /** Field message, e.g. from a 422 `rating_invalid`. */
  issue?: string;
}

export function SetupFields({ goal, onGoal, disabled, issue }: SetupFieldsProps) {
  const id = useId();
  const c = softCount(goal, LIMITS.item);
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="min-h-0 text-base font-semibold">
        Change goal
      </Label>
      <Textarea
        id={id}
        required
        rows={2}
        value={goal}
        disabled={disabled}
        aria-invalid={issue ? true : undefined}
        aria-describedby={issue ? "change-goal-issue" : undefined}
        onChange={(e) => onGoal(e.target.value)}
      />
      <span className={c.over ? "text-sm font-semibold text-destructive" : "text-sm text-muted-foreground"}>
        {c.length.toLocaleString("en-US")} / {c.limit.toLocaleString("en-US")}
        {c.over ? " — over the limit; shorten it before it can be saved" : ""}
      </span>
      {issue ? (
        <span id="change-goal-issue" role="alert" className="text-sm text-destructive">
          {issue}
        </span>
      ) : null}
    </div>
  );
}
