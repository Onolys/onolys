import { Chip } from '../../ui/Chip';
import { Note } from '../../ui/Note';
import type { ModelLane } from '../compareApi';
import '../lineView.css';

export interface LaneTurn { id: string; speaker: string; is_clinician: boolean; text: string }
export const laneLabel = (value: string[]) => value.length ? value.join(', ') : 'none';

/**
 * Transcript lane table: turn, speaker chip, text, human lane, one chip per combo lane.
 * Fixed layout (no horizontal scroll); rows stack as cards on narrow screens. Disagreeing rows are amber with a warning mark.
 */
export function LaneTable({ turns, selected, human, lane, letter, unavailable, disagrees, isDisagreement, expanded, toggle, inspect, setTrigger }: {
 turns: LaneTurn[]; selected: string[]; human: Record<string, string[]>; lane: (key: string) => ModelLane | undefined;
 letter: (key: string) => string; unavailable: (key: string, turnId: string) => string | null;
 disagrees: (key: string, turnId: string) => boolean; isDisagreement: (turnId: string) => boolean;
 expanded: Record<string, boolean>; toggle: (turnId: string) => void;
 inspect: (turnId: string, trigger: HTMLElement) => void; setTrigger: (turnId: string, node: HTMLButtonElement | null) => void;
}) {
 return <div className="line-lanes">
  <table>
   <caption>Transcript and saved line codes</caption>
   <thead><tr><th scope="col">Turn</th><th scope="col">Speaker</th><th scope="col">Transcript</th><th scope="col">Human</th><th scope="col">Combo lanes</th></tr></thead>
   <tbody>{turns.map(turn => {
    const differing = selected.filter(key => unavailable(key, turn.id) || human[turn.id] === undefined || disagrees(key, turn.id));
    const agreeing = selected.filter(key => !differing.includes(key));
    const shown = selected.length > 5 && !expanded[turn.id] ? differing : selected;
    const flagged = isDisagreement(turn.id);
    return <tr key={turn.id} data-turn={turn.id} className={flagged ? 'line-disagree' : undefined}>
     <th scope="row" data-label="Turn"><button type="button" ref={node => setTrigger(turn.id, node)} aria-label={`Inspect turn ${turn.id}`} onClick={event => inspect(turn.id, event.currentTarget)}>{turn.id}</button>{flagged && <span aria-label="Disagreement"> <Chip tone="warning">Disagrees</Chip></span>}</th>
     <td data-label="Speaker" className="line-verbatim"><Chip tone={turn.is_clinician ? 'info' : 'neutral'}>{turn.speaker}</Chip></td>
     <td data-label="Transcript" data-transcript className="line-verbatim">{turn.text}</td>
     <td data-label="Human" data-human>{human[turn.id] === undefined ? '' : laneLabel(human[turn.id])}</td>
     <td data-label="Combo lanes">{shown.map(key => <p className="line-chip" key={key}>{unavailable(key, turn.id) ? <><span>{letter(key)}: </span><span>{unavailable(key, turn.id)}</span></> : `${letter(key)}: ${lane(key)?.turns[turn.id]?.map(laneLabel).join(' / ') ?? ''}`}</p>)}{selected.length > 5 && agreeing.length > 0 && <button type="button" onClick={() => toggle(turn.id)}>{expanded[turn.id] ? 'Collapse agreement' : `+${agreeing.length} agree`}</button>}</td>
    </tr>;
   })}</tbody>
  </table>
  {turns.length === 0 && <p>No matching lines</p>}
  <Note>How to read: Human cells are blank when no label was saved; none means an explicitly empty label. A warning mark flags a disagreement. Combo codes appear in repeat order.</Note>
 </div>;
}
