import { Chip } from '../../ui/Chip';
import { winShareTint } from '../../ui/chart/theme';
import { ComboTag } from '../../ui/ComboTag';
import type { CompareAnalysis } from '../compareApi';
import type { ComboLegendEntry } from '../compareTypes';
import type { FailedCombo } from '../failedCombos';
import './matrix.css';

type Pair = CompareAnalysis['head_to_head'][number];
const na = (reason?: string) => `n/a${reason ? ` - ${reason}` : ''}`;

/** Head-to-head matrix: "row closer than column on N of M sessions", tinted by win share with a text verdict (never colour alone), ties noted. Counts are the server's; failed combos are greyed and never compared. */
export function HeadToHead({ data, legend, failed }: { data: CompareAnalysis; legend: ComboLegendEntry[]; failed: FailedCombo[] }) {
 const failedAll = new Map(failed.filter(f => f.all).map(f => [f.combo_key, f]));
 const index = (key: string) => Math.max(0, legend.findIndex(e => e.combo.combo_key === key));
 const letter = (key: string) => legend.find(e => e.combo.combo_key === key)?.letter ?? key;
 const head = (key: string) => <><ComboTag index={index(key)} letter={letter(key)} />{data.skipped_combos.includes(key) && <Chip tone="muted">skipped</Chip>}{failedAll.has(key) && <Chip tone="danger">failed</Chip>}</>;
 const pairOf = (r: string, c: string): Pair | undefined => data.head_to_head.find(p => p.a === r && p.b === c || p.b === r && p.a === c);
 const cell = (r: string, c: string) => {
  if (r === c) return <td key={c} className="mx-self">Same combo</td>;
  if (failedAll.has(r) || failedAll.has(c)) return <td key={c} className="mx-muted">—</td>;
  const pair = pairOf(r, c);
  if (!pair) return <td key={c} className="mx-muted">n/a</td>;
  if (pair.na) return <td key={c} className="mx-muted">{na(pair.na.reason)} · n={pair.n}</td>;
  const wins = pair.a === r ? pair.a_closer : pair.b_closer, losses = pair.a === r ? pair.b_closer : pair.a_closer;
  const verdict = wins > losses ? 'ahead' : wins < losses ? 'behind' : 'even';
  const share = wins + losses ? wins / (wins + losses) : 0.5;
  return <td key={c} className={`mx-cell mx-${verdict}`} data-verdict={verdict} data-win-share={Number(share.toFixed(2))} style={{ backgroundColor: winShareTint(share) }}
   aria-label={`${letter(r)} closer than ${letter(c)} on ${wins} of ${pair.n} sessions, ${pair.ties} ties`}>
   <b>{wins} of {pair.n}</b><span className="mx-sub">{verdict} · {pair.ties} {pair.ties === 1 ? 'tie' : 'ties'}</span>
  </td>;
 };
 return <section className="mx-card" aria-label="Head-to-head">
  <h3 className="mx-title">Head-to-head</h3>
  <p className="mx-caption">How often the row combo was closer to the human count than the column combo, out of the sessions both completed.</p>
  <table className="mx-table" aria-label="Head-to-head">
   <caption className="ui-sr">Row combo compared with column combo</caption>
   <thead><tr><th scope="col" className="mx-corner">Closer ↓ / than →</th>{data.combos.map(c => <th scope="col" key={c.combo_key} className={failedAll.has(c.combo_key) ? 'mx-muted' : undefined}>{head(c.combo_key)}</th>)}</tr></thead>
   <tbody>{data.combos.map(row => <tr key={row.combo_key} className={failedAll.has(row.combo_key) ? 'mx-failed' : undefined}><th scope="row">{head(row.combo_key)}</th>{data.combos.map(col => cell(row.combo_key, col.combo_key))}</tr>)}</tbody>
  </table>
  <p className="mx-note">Ties count for neither combo. Shade shows the row combo's win share among decided sessions: green above half, red below, white at half.</p>
 </section>;
}
