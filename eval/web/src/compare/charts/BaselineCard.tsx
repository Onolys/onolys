import { StatTile } from '../../ui/StatTile';
import type { CompareAnalysis } from '../compareApi';

/** Human-vs-human baseline: always n/a today; the server's reason (needs a second human coder) is shown as plain text. */
export function BaselineCard({ baseline }: { baseline: CompareAnalysis['baseline'] }) {
 const reason = baseline.na?.reason;
 const hasValue = !baseline.na && baseline.value !== null;
 return <section className="rel-baseline" aria-label="Human-vs-human baseline">
  <h3 className="rel-title">Human-vs-human baseline</h3>
  <StatTile label="Inter-rater agreement" value={hasValue ? `${Math.round((baseline.value ?? 0) * 100)}%` : 'n/a'} sub={hasValue ? `n=${baseline.n}` : reason ? reason.charAt(0).toUpperCase() + reason.slice(1) : undefined} />
 </section>;
}
