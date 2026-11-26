import { Chip } from '../../ui/Chip';
import type { CompareUrlState } from '../compareUrl';
import type { ComboLegendEntry } from '../compareTypes';

export const LINE_CODES = ['affirm', 'confront', 'cr', 'emphasize_autonomy', 'gi', 'persuade', 'persuade_permission', 'question', 'seek_collab', 'sr', 'none', 'multi'];

export interface LineSessionOption { session_id: string; matched_lines: number | null }

/** Line view filter bar: session, human/prediction code, combo, only-disagreements, plus the differing-lines count chip. */
export function LineFilters({ state, sessionId, sessions, selected, legend, letter, differing, change }: {
 state: CompareUrlState; sessionId: string; sessions: LineSessionOption[]; selected: string[]; legend: ComboLegendEntry[];
 letter: (key: string) => string; differing: number; change: (next: Partial<CompareUrlState>) => void;
}) {
 return <>
  <div className="line-filters">
   <label>Session<select value={state.session ?? sessionId} onChange={event => change({ session: event.target.value })}>{sessions.map(item => <option key={item.session_id} value={item.session_id}>{item.session_id} · {item.matched_lines === null ? 'unavailable' : `${item.matched_lines} matched lines`}</option>)}</select></label>
   <label>Human code<select value={state.code ?? ''} onChange={event => change({ code: event.target.value || undefined })}><option value="">All codes</option>{LINE_CODES.map(code => <option key={code}>{code}</option>)}</select></label>
   <label>Prediction code<select value={state.metric ?? ''} onChange={event => change({ metric: event.target.value || undefined })}><option value="">All predictions</option>{LINE_CODES.map(code => <option key={code}>{code}</option>)}</select></label>
   <label>Combo<select value={state.combo ?? ''} onChange={event => change({ combo: event.target.value || undefined })}><option value="">All selected combos</option>{selected.map(key => <option key={key} value={key}>{letter(key)} · {key}</option>)}</select></label>
   <label><input type="checkbox" checked={state.only === 'disagree'} onChange={event => change({ only: event.target.checked ? 'disagree' : undefined })}/>Only disagreements</label>
   <span className="line-differing"><Chip tone={differing > 0 ? 'warning' : 'muted'}>{differing} differing {differing === 1 ? 'line' : 'lines'}</Chip></span>
  </div>
  <fieldset><legend>Combo lanes</legend>{legend.map(item => <label key={item.combo.combo_key}><input type="checkbox" checked={selected.includes(item.combo.combo_key)} onChange={event => {
   const next = event.target.checked ? [...selected, item.combo.combo_key] : selected.filter(key => key !== item.combo.combo_key);
   if (next.length) change({ combos: next });
  }}/>{item.letter} · {item.label}</label>)}</fieldset>
 </>;
}
