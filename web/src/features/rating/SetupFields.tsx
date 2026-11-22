/**
 * Session setup on the upload screen (PRD R3, D3): one required "Change goal" field, shown only
 * while the rating UI is off. Reuses the card helpers for validation and the PUT payload; the
 * rating card itself is untouched. The coded span is never sent (the engine picks it, D3d).
 */
import { buildCard, emptyForm, localIssues, type Card } from "./card";

const formFor = (goal: string) => ({ ...emptyForm(), changeGoal: goal });

/** Local blockers for the goal (blank). Empty object when fine. */
export const goalIssues = (goal: string) => localIssues(formFor(goal), { noRating: true });

/** Final no-rating card carrying only the goal. */
export const goalCard = (goal: string): Card => buildCard(formFor(goal), { noRating: true });

export interface SetupFieldsProps {
  goal: string;
  onGoal: (v: string) => void;
  /** Field message, e.g. from a 422 `rating_invalid`. */
  issue?: string;
}

export function SetupFields({ goal, onGoal, issue }: SetupFieldsProps) {
  return (
    <label>
      Change goal
      <input
        type="text"
        required
        value={goal}
        aria-invalid={issue ? true : undefined}
        aria-describedby={issue ? "change-goal-issue" : undefined}
        onChange={(e) => onGoal(e.target.value)}
      />
      {issue ? (
        <span id="change-goal-issue" role="alert" className="field-error">
          {issue}
        </span>
      ) : null}
    </label>
  );
}
