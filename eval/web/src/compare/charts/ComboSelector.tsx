import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import { Note } from '../../ui/Note';
import type { CompareOverview } from '../compareApi';
import type { ComboLegendEntry } from '../compareTypes';
import type { FailedCombo } from '../failedCombos';
import '../deepDive.css';

export interface Paired { n: number; of: number }

/** Sessions paired across the chosen combos: fewest paired (n) over the largest planned (of), from the overview's Count error cells. */
export function pairedSessions(overview: Pick<CompareOverview, 'count_error'>, keys: string[]): Paired | null {
 const cells = keys.map(key => overview.count_error[key]).filter(cell => cell && !cell.na);
 if (!cells.length) return null;
 return { n: Math.min(...cells.map(cell => cell.n)), of: Math.max(...cells.map(cell => cell.of)) };
}

/** Combo picker card: Human is fixed on; each combo is a toggle chip (letter + shape + colour); failed combos are greyed and disabled. */
export function ComboSelector({ legend, failed, selected, paired, onChange }: { legend: ComboLegendEntry[]; failed: FailedCombo[]; selected: string[]; paired: Paired | null; onChange: (keys: string[]) => void }) {
 const failures = new Map(failed.filter(item => item.all).map(item => [item.combo_key, item]));
 return <section className="deep-card deep-selector" aria-labelledby="deep-selector-title">
  <header className="deep-card-head"><div><h3 id="deep-selector-title">Compare combos</h3><Note>Human is always shown. Top 3 by Count error are selected by default.</Note></div>
   {paired && <Chip tone="muted" icon={<span aria-hidden="true"/>}>{`paired ${paired.n} of ${paired.of} sessions`}</Chip>}</header>
  <div className="deep-toggles" role="group" aria-label="Combos to compare">
   <button type="button" className="deep-toggle is-on" aria-pressed="true" disabled title="Human labels are always shown"><span className="deep-human-swatch" aria-hidden="true"/>Human</button>
   {legend.map((item, index) => {
    const key = item.combo.combo_key, fail = failures.get(key), on = !fail && selected.includes(key);
    const last = on && selected.filter(k => !failures.has(k)).length <= 1;
    return <button key={key} type="button" className={`deep-toggle${on ? ' is-on' : ''}${fail ? ' is-failed' : ''}`} aria-pressed={on} aria-label={`${item.letter} · ${item.label}${fail ? `, failed: ${fail.code}` : ''}`} disabled={Boolean(fail) || last} title={fail ? `All runs failed: ${fail.code}` : undefined}
     onClick={() => onChange(on ? selected.filter(k => k !== key) : [...selected, key])}>
     <ComboTag index={index} letter={item.letter}/><span className="deep-toggle-label">{item.label}</span>{fail && <span className="deep-toggle-fail">failed: {fail.code}</span>}
    </button>;
   })}
  </div>
 </section>;
}
