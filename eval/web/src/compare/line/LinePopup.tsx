import type { RefObject } from 'react';
import { AppDialog } from '../../ui/AppDialog';
import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import type { CompareTurn } from '../compareApi';
import { ErrorNotice, Snippets } from './lineShared';
import { laneLabel } from './LaneTable';
import '../lineView.css';

const codeSet = (codes: string[]) => [...new Set(codes)].sort().join('\u0000');

/** Line popup: line text, human code, each combo's codes + rationale, and "k of r repeats agree". Focus returns to the clicked line button. */
export function LinePopup({ turnId, selected, letter, index, loaded, unavailable, retry, onClose, returnFocus }: {
 turnId: string | undefined; selected: string[]; letter: (key: string) => string; index: (key: string) => number;
 loaded: { data?: CompareTurn; error?: unknown } | undefined; unavailable: (key: string, turnId: string) => string | null;
 retry: () => void; onClose: () => void; returnFocus: RefObject<HTMLElement | null>;
}) {
 const turn = loaded?.data;
 const humanLabel = turn?.human ? laneLabel(turn.human.codes) : null;
 // Order-insensitive: the server sorts combo codes but not human codes. The turn payload carries no scored-code set, so sets are compared as-is.
 const humanSet = turn?.human ? codeSet(turn.human.codes) : null;
 return <AppDialog open={Boolean(turnId)} onOpenChange={open => { if (!open) onClose(); }} title={`Turn ${turnId ?? ''}`} description="Saved human labels and combo output" returnFocus={returnFocus}>
  <div className="line-dialog">
   {!loaded && <p role="status">Loading line…</p>}
   {loaded?.error !== undefined && <ErrorNotice error={loaded.error} retry={retry} />}
   {turn && <>
    <p className="line-verbatim">{turn.text}</p>
    <section className="line-dialog-card"><h3 className="line-dialog-heading">Human</h3>
     <p>{turn.human ? <Chip tone="neutral" mono>{humanLabel}</Chip> : ''}</p>
    {turn.human?.note != null && <p className="line-verbatim">{turn.human.note}</p>}</section>
    {selected.map(key => {
     const item = turn.combos[key];
     return <section key={key} className="line-dialog-card"><h3 className="line-dialog-heading"><ComboTag index={index(key)} letter={letter(key)} /> {key}</h3>
      {!item || item.missing || item.codes.length === 0 ? <p>{item?.missing ?? unavailable(key, turn.turn_id) ?? 'no completed runs'}</p> : <>
       <p className="line-dialog-codes">{item.codes.map((codes, i) => { const label = laneLabel(codes); return <Chip key={i} tone={humanSet !== null && codeSet(codes) !== humanSet ? 'warning' : 'neutral'} mono>{label}</Chip>; })}</p><Snippets snippets={item.rationales} />
       {item.agree && <p>{item.agree.k} of {item.agree.r} repeats agree</p>}
      </>}
     </section>;
    })}
   </>}
  </div>
 </AppDialog>;
}
