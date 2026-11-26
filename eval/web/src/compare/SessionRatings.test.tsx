// @vitest-environment jsdom
import type { ComponentProps } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { LineView } from './LineView';
import { ratingChip } from './line/SessionRatings';
import { createEvalApi } from '../api';
import type { CompareLines, CompareOverview, CompareTurn } from './compareApi';
import linesFixture from './fixtures/lines.json';
import overviewFixture from './fixtures/overview.json';
import turnFixture from './fixtures/turn.json';
afterEach(cleanup);
const vp = (p: unknown) => p as ComponentProps<typeof LineView>;
function props() {
 const data = structuredClone(linesFixture) as CompareLines, overview = structuredClone(overviewFixture) as CompareOverview;
 const [a, b] = data.combos.map(c => c.combo_key);
 data.globals = { human: { cct: 4, empathy: 3 }, combos: { [a]: [{ cct: 4, empathy: 2 }, { cct: 3, empathy: 1 }], [b]: [{ cct: 4, empathy: 3 }] } };
 const popup = structuredClone(turnFixture) as CompareTurn;
 popup.turn_id = 't5'; popup.text = 'Popup line text.'; popup.human = { codes: ['sr'], note: null };
 popup.combos[a] = { missing: null, codes: [['sr'], ['cr'], ['sr']], rationales: [{ session_id: data.session_id, combo_key: a, repeat: 1, rationale: 'Because reasons.', withheld: false }], agree: { k: 2, r: 3 } };
 const api = { ...createEvalApi('', vi.fn()), compareTurn: vi.fn().mockResolvedValue(popup), compareReasoning: vi.fn().mockResolvedValue({ ...linesFixture, groups: [], next_cursor: null }) };
 return { data, overview, api, runId: 'r1', state: { view: 'compare' as const, run: 'r1', tab: 'lines' as const, session: data.session_id }, navigate: vi.fn(), legend: data.combos.map((combo, i) => ({ combo, letter: String.fromCharCode(65 + i), label: combo.combo_key })) };
}
it('ratingChip tones carry text', () => {
 expect(ratingChip(4, 4)).toEqual({ tone: 'success', text: 'exact' });
 expect(ratingChip(3, 4)).toEqual({ tone: 'warning', text: 'off 1' });
 expect(ratingChip(1, 4)).toEqual({ tone: 'danger', text: 'off 2+' });
 expect(ratingChip(undefined, 4).text).toBe('n/a');
});
it('keeps global ratings collapsed by default, with no request, then shows exact/off1/off2+ chips with text', async () => {
 const p = props(); const { container } = render(<LineView {...vp(p)} />);
 expect(screen.queryByRole('table', { name: 'Session global ratings' })).toBeNull(); expect(p.api.compareReasoning).not.toHaveBeenCalled();
 const toggle = screen.getByRole('button', { name: 'Show global ratings' }); expect(toggle.getAttribute('aria-expanded')).toBe('false');
 fireEvent.click(toggle);
 const table = await screen.findByRole('table', { name: 'Session global ratings' });
 const chips = [...table.querySelectorAll('.ui-chip')].map(c => c.textContent);
 expect(chips).toEqual(expect.arrayContaining(['4 · exact', '3 · off 1', '1 · off 2+']));
 expect(table.querySelector('.ui-chip-success svg')).toBeTruthy(); expect(table.querySelector('.ui-chip-warning svg')).toBeTruthy(); expect(table.querySelector('.ui-chip-danger svg')).toBeTruthy();
 expect(container.querySelector('.table-scroll')).toBeNull();
});
it('shows reasoning only inside a collapsed disclosure', async () => {
 const p = props(); const a = p.data.combos[0].combo_key;
 p.api.compareReasoning.mockResolvedValue({ ...linesFixture, groups: [{ code: 'cct', snippets: [{ session_id: p.data.session_id, combo_key: a, repeat: 1, rationale: 'Why cct.', withheld: false }] }], next_cursor: null });
 render(<LineView {...vp(p)} />); fireEvent.click(screen.getByRole('button', { name: 'Show global ratings' }));
 const reasoning = await screen.findByRole('button', { name: 'Show reasoning' }); expect(screen.queryByText('Why cct.')).toBeNull();
 fireEvent.click(reasoning); expect(screen.getByText('Why cct.')).toBeTruthy();
});
it('popup shows line text, human code, combo codes + rationale, agreement, and returns focus', async () => {
 const p = props(); const view = render(<LineView {...vp(p)} />);
 const trigger = screen.getByRole('button', { name: 'Inspect turn t5' }); trigger.focus(); fireEvent.click(trigger);
 view.rerender(<LineView {...vp(p)} state={{ ...p.state, turn: 't5' }} />);
 const dialog = await screen.findByRole('dialog'); await within(dialog).findByText('Popup line text.');
 expect(within(dialog).getAllByText('sr', { selector: '.ui-chip' }).length).toBeGreaterThanOrEqual(1); expect(within(dialog).getByText('Because reasons.')).toBeTruthy();
 expect(within(dialog).getAllByText('cr', { selector: '.ui-chip-warning' })).toHaveLength(1); expect(within(dialog).getByText('2 of 3 repeats agree')).toBeTruthy();
 expect(within(dialog).getAllByRole('img', { name: /^Combo / }).length).toBeGreaterThan(0);
 fireEvent.keyDown(dialog, { key: 'Escape' }); view.rerender(<LineView {...vp(p)} />);
 await waitFor(() => expect(document.activeElement).toBe(trigger));
});
