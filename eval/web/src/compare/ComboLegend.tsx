import { Chip } from '../ui/Chip';
import { ComboTag } from '../ui/ComboTag';
import { EvalLink, type CompareNavigate } from './CompareLink';
import type { ComboLegendEntry } from './compareTypes';
import type { CompareUrlState } from './compareUrl';
import type { FailedCombo } from './failedCombos';
import './comboLegend.css';

/** Combo identity shown once above the tabs: letter tag, model/engine/tier/effort label, failed flag. The tag links to that combo's deep dive. */
export function ComboLegend({ legend, failed, state, navigate }: { legend: ComboLegendEntry[]; failed: FailedCombo[]; state: CompareUrlState; navigate: CompareNavigate }) {
 const failures = new Map(failed.filter(item => item.all).map(item => [item.combo_key, item]));
 return <section className="compare-legend" aria-label="Combo legend"><ul>
  {legend.map((item, index) => {
   const fail = failures.get(item.combo.combo_key);
   return <li key={item.combo.combo_key} className={fail ? 'is-failed' : undefined}>
    <EvalLink state={{ ...state, view: 'compare', tab: 'deep', combos: [item.combo.combo_key] }} navigate={navigate}><ComboTag index={index} letter={item.letter}/></EvalLink>
    <span className="compare-legend-label">{item.label}</span>
    {fail && <Chip tone="danger">failed: {fail.code}</Chip>}
   </li>;
  })}
 </ul></section>;
}
