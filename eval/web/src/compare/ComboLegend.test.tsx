// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CompareOverview } from './compareApi';
import { ComboLegend } from './ComboLegend';
import overviewFixture from './fixtures/overview.json';
afterEach(cleanup);
const base = overviewFixture as unknown as CompareOverview;
const legend = base.combos.map((combo, index) => ({ combo, letter: String.fromCharCode(65 + index), label: `miti · model-${index} · low` }));

it('lists each combo once with letter tag, label and a deep-dive link', () => {
 render(<ComboLegend legend={legend} failed={[]} state={{ view: 'compare', run: 'r1' }} navigate={vi.fn()}/>);
 const region = screen.getByRole('region', { name: 'Combo legend' });
 const items = within(region).getAllByRole('listitem');
 expect(items).toHaveLength(2);
 expect(within(items[0]).getByRole('img', { name: 'Combo A' })).toBeTruthy();
 expect(within(items[1]).getByRole('img', { name: 'Combo B' })).toBeTruthy();
 expect(within(items[0]).getByText('miti · model-0 · low')).toBeTruthy();
 expect(within(items[0]).getByRole('link', { name: 'Combo A' }).getAttribute('href')).toContain(`combos=${encodeURIComponent(base.combos[0].combo_key)}`);
 expect(within(region).queryByText('failed', { exact: false })).toBeNull();
});
it('flags a failed combo with its error code and a tinted row', () => {
 render(<ComboLegend legend={legend} failed={[{ combo_key: base.combos[1].combo_key, code: 'invalid_parameters', runs: 4, all: true }]} state={{ view: 'compare', run: 'r1' }} navigate={vi.fn()}/>);
 const items = screen.getAllByRole('listitem');
 expect(within(items[1]).getByText('failed: invalid_parameters').className).toContain('ui-chip-danger');
 expect(items[1].className).toContain('is-failed');
 expect(items[0].className).not.toContain('is-failed');
});
