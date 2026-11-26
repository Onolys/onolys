import type { RefObject } from 'react';
import { AppDialog } from '../../ui/AppDialog';
import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import type { CompareTurn } from '../compareApi';
import { ErrorNotice, Snippets } from './lineShared';
import { laneLabel } from './LaneTable';
import '../lineView.css';

/** Line popup: line text, human code, each combo's codes + rationale, and "k of r repeats agree". Focus returns to the clicked line button. */
export function LinePopup({ turnId, selected, letter, loaded, unavailable, retry, onClose, returnFocus }: {
 turnId: string | undefined; selected: string[]; letter: (key: string) => string;
 loaded: { data?: CompareTurn; error?: unknown } | undefined; unavailable: (key: string, turnId: string) => string | null;
 retry: () => void; onClose: () => void; returnFocus: RefObject<HTMLElement | null>;
}) {
 const turn = loaded?.data;
 return <AppDialog open={Boolean(turnId)} onOpenChange={open => { if (!open) onClose(); }} title={`Turn ${turnId ?? ''}`} description="Saved human labels and combo output" returnFocus={returnFocus}>
  <div className="line-dialog">
   {!loaded && <p role="status">Loading line…</p>}
   {loaded?.error !== undefined && <ErrorNotice error={loaded.error} retry={retry} />}
   {turn && <>
    <p className="line-verbatim">{turn.text}</p>
    <h3>Human</h3>
    <p>{turn.human ? <Chip tone="info">{laneLabel(turn.human.codes)}</Chip> : ''}</p>
    {turn.human?.note != null && <p className="line-verbatim">{turn.human.note}</p>}
    {selected.map((key, index) => {
     const item = turn.combos[key];
     return <section key={key}><h3><ComboTag index={index} letter={letter(key)} /> {key}</h3>
      {!item || item.missing || item.codes.length === 0 ? <p>{item?.missing ?? unavailable(key, turn.turn_id) ?? 'no completed runs'}</p> : <>
       <p>{item.codes.map(laneLabel).join(' / ')}</p><Snippets snippets={item.rationales} />
       {item.agree && <p>{item.agree.k} of {item.agree.r} repeats agree</p>}
      </>}
     </section>;
    })}
   </>}
  </div>
 </AppDialog>;
}
