import { Chip } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import { Note } from '../../ui/Note';
import type { ModelLane } from '../compareApi';
import '../lineView.css';

export interface LaneTurn { id: string; speaker: string; is_clinician: boolean; text: string }
export const MAX_LANES = 3;
export const laneLabel = (value: string[]) => value.length ? value.join(', ') : 'none';

/**
 * Transcript lane table: turn, speaker chip, text, human lane, one column per combo lane (at most 3; the Combo lanes filter picks which).
 * Fixed layout (no horizontal scroll); rows stack as cards on narrow screens. Disagreeing rows are amber with a warning mark.
 */
export function LaneTable({ turns, selected, human, lane, letter, index, unavailable, isDisagreement, inspect, setTrigger }: {
 turns: LaneTurn[]; selected: string[]; index: (key: string) => number; human: Record<string, string[]>; lane: (key: string) => ModelLane | undefined;
 letter: (key: string) => string; unavailable: (key: string, turnId: string) => string | null;
 isDisagreement: (turnId: string) => boolean;
 inspect: (turnId: string, trigger: HTMLElement) => void; setTrigger: (turnId: string, node: HTMLButtonElement | null) => void;
}) {
 return <div className="line-lanes">
  <table>
   <caption>Transcript and saved line codes</caption>
   <thead><tr><th scope="col">Turn</th><th scope="col">Speaker</th><th scope="col">Transcript</th><th scope="col">Human</th>{selected.map(key => <th scope="col" key={key}><ComboTag index={index(key)} letter={letter(key)} /></th>)}</tr></thead>
   <tbody>{turns.map(turn => {
    const flagged = isDisagreement(turn.id);
    return <tr key={turn.id} data-turn={turn.id} className={flagged ? 'line-disagree' : undefined}>
     <th scope="row" data-label="Turn"><button type="button" ref={node => setTrigger(turn.id, node)} aria-label={`Inspect turn ${turn.id}`} onClick={event => inspect(turn.id, event.currentTarget)}>{turn.id}</button>{flagged && <span aria-label="Disagreement"> <Chip tone="warning">Disagrees</Chip></span>}</th>
     <td data-label="Speaker" className="line-verbatim"><Chip tone={turn.is_clinician ? 'info' : 'neutral'}>{turn.speaker}</Chip></td>
     <td data-label="Transcript" data-transcript className="line-verbatim">{turn.text}</td>
     <td data-label="Human" data-human>{human[turn.id] === undefined ? '' : laneLabel(human[turn.id])}</td>
     {selected.map(key => <td key={key} data-label={`Combo ${letter(key)}`}><p className="line-chip">{unavailable(key, turn.id) ?? lane(key)?.turns[turn.id]?.map(laneLabel).join(' / ') ?? ''}</p></td>)}
    </tr>;
   })}</tbody>
  </table>
  {turns.length === 0 && <p>No matching lines</p>}
  <Note>How to read: Human cells are blank when no label was saved; none means an explicitly empty label. A warning mark flags a disagreement. Combo codes appear in repeat order.</Note>
 </div>;
}
