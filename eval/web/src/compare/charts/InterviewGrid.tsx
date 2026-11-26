import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import { EvalLink, type CompareNavigate } from '../CompareLink';
import type { CompareAnalysis } from '../compareApi';
import type { ComboLegendEntry } from '../compareTypes';
import type { FailedCombo } from '../failedCombos';
import './matrix.css';

const na = (reason?: string) => `n/a${reason ? ` - ${reason}` : ''}`;

/** Interviews by combo: session x combo Count error with n and repeats. Shading scales with the server's error value (display only; the number is always printed). Session cells open that session in Line view. */
export function InterviewGrid({ data, legend, failed, runId, navigate }: { data: CompareAnalysis; legend: ComboLegendEntry[]; failed: FailedCombo[]; runId: string; navigate: CompareNavigate }) {
 const failedAll = new Map(failed.filter(f => f.all).map(f => [f.combo_key, f]));
 const index = (key: string) => Math.max(0, legend.findIndex(e => e.combo.combo_key === key));
 const letter = (key: string) => legend.find(e => e.combo.combo_key === key)?.letter ?? key;
 const maxOff = Math.max(0, ...data.grid.flatMap(r => Object.values(r.cells).map(c => c.off ?? 0))) || 1;
 return <section className="mx-card" aria-label="Interviews by combo">
  <h3 className="mx-title">Interviews by combo</h3>
  <p className="mx-caption">Count error per session and combo (repeats averaged); darker is larger. Open a session to see its lines.</p>
  {data.grid.length ? <table className="mx-table" aria-label="Interviews by combo">
   <caption className="ui-sr">Session Count error, paired n, successful repeats and labeled codes</caption>
   <thead><tr><th scope="col" className="mx-corner">Session</th>{data.combos.map(c => <th scope="col" key={c.combo_key} className={failedAll.has(c.combo_key) ? 'mx-muted' : undefined}><ComboTag index={index(c.combo_key)} letter={letter(c.combo_key)} />{data.skipped_combos.includes(c.combo_key) && <Chip tone="muted">skipped</Chip>}{failedAll.has(c.combo_key) && <Chip tone="danger">failed</Chip>}</th>)}</tr></thead>
   <tbody>{data.grid.map(row => <tr key={row.session_id}>
    <th scope="row"><EvalLink state={{ run: runId, view: 'compare', tab: 'lines', session: row.session_id }} navigate={navigate}>{row.session_id}</EvalLink></th>
    {data.combos.map(c => {
     const cell = row.cells[c.combo_key];
     if (failedAll.has(c.combo_key)) return <td key={c.combo_key} className="mx-muted">—</td>;
     if (!cell) return <td key={c.combo_key} className="mx-muted">n/a</td>;
     if (cell.na || cell.off === null) return <td key={c.combo_key} className="mx-muted">{na(cell.na?.reason)} · n={cell.n}</td>;
     const shade = Math.round(Math.min(1, cell.off / maxOff) * 28);
     return <td key={c.combo_key} className="mx-cell mx-grid" style={{ background: `color-mix(in srgb, var(--ui-low) ${shade}%, #fff)` }} title={`${cell.codes_labeled} codes labeled`}>
      <b>off {cell.off}</b><span className="mx-sub">n={cell.n} · {cell.repeats} repeats</span>
     </td>;
    })}
   </tr>)}</tbody>
  </table> : <p className="mx-empty">No session results available</p>}
 </section>;
}
