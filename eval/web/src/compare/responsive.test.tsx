// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { cleanup, render, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi } from '../api';
import { Overview } from './Overview';
import { DeepDive } from './DeepDive';
import { MoreAnalysis } from './MoreAnalysis';
import { LineView } from './LineView';
import type { CompareOverview, CompareDeepDive, CompareAnalysis, CompareLines } from './compareApi';
import overview from './fixtures/overview.json';
import deep from './fixtures/deepDive.json';
import analysis from './fixtures/analysis.json';
import lines from './fixtures/lines.json';

afterEach(cleanup);
const css = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8');
const styles = ['compare.css', 'overview.css', 'deepDive.css', 'moreAnalysis.css', 'lineView.css'].map(css).join('\n');
const sheet = document.createElement('style');
sheet.textContent = styles;
document.head.append(sheet);

// jsdom does not lay out pages. Verify the actual CSS breakpoint contract and
// semantic scroll/chart structure; the owner's browser check verifies pixels.
it.each([320, 768, 1280])('retains accessible chart/table structure at the %ipx breakpoint', width => {
 Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
 const data = overview as CompareOverview;
 const props = {
  overview: data, state: { view: 'compare' as const, run: 'r1' }, runId: 'r1', navigate: vi.fn(),
  api: { ...createEvalApi('', vi.fn()), compareReasoning: vi.fn().mockResolvedValue({ groups: [], next_cursor: null }) },
  legend: data.combos.map((combo, index) => ({ combo, letter: String.fromCharCode(65 + index), label: combo.combo_key })),
 };
 const view = render(<>
  <Overview {...props} data={data}/>
  <DeepDive {...props} data={deep as CompareDeepDive}/>
  <MoreAnalysis {...props} data={analysis as CompareAnalysis}/>
  <LineView {...props} data={lines as CompareLines}/>
 </>);
 const regions = view.container.querySelectorAll('[role="region"]');
 expect(regions.length).toBeGreaterThan(10);
 regions.forEach(region => {
  expect(region.getAttribute('aria-label')).toBeTruthy();
  expect(region.getAttribute('tabindex')).toBe('0');
 });
 view.container.querySelectorAll('.compare-chart').forEach(chart => {
  expect(chart.querySelector('h3')?.id).toBe(chart.getAttribute('aria-labelledby'));
  expect(within(chart as HTMLElement).getByText('How to read:')).toBeTruthy();
  expect(chart.querySelector('details summary')?.textContent).toMatch(/^Show data table/);
  expect(chart.querySelector('details table caption')).toBeTruthy();
  expect(chart.querySelector('details table th[scope="row"], details table th[scope="col"]')).toBeTruthy();
 });
 const heatmap = view.container.querySelector('.overview-heatmap')!;
 expect(heatmap.getAttribute('aria-describedby')).toBe('overview-heatmap-caption');
 expect(document.getElementById('overview-heatmap-caption')?.textContent).toContain('How to read:');
 const rules = [...sheet.sheet!.cssRules];
 const media = rules.filter((rule): rule is CSSMediaRule => rule.type === CSSRule.MEDIA_RULE);
 const mobile = media.filter(rule => rule.conditionText.replaceAll(' ', '') === '(max-width:760px)');
 expect(mobile.length).toBeGreaterThan(0);
 const stacked = mobile.flatMap(rule => [...rule.cssRules]).find(rule => rule.cssText.includes('.overview-leaderboard tbody'));
 expect(stacked?.cssText).toContain('display: block');
 expect(width <= 760).toBe(width === 320);
 expect(styles).toMatch(/\.overview-row-label\s*\{[^}]*position:\s*sticky;[^}]*left:\s*0/);
 expect(styles).toMatch(/\.overview-scroll\s*\{[^}]*max-width:\s*100%;[^}]*overflow-x:\s*auto/);
 // Wide content uses scroll containers, not a fixed pixel width on a page.
 expect(styles).not.toMatch(/(?:^|[;{])\s*width:\s*\d+px/);
 expect(view.container.querySelector('[style*="width: 320px"], [style*="width: 768px"], [style*="width: 1280px"]')).toBeNull();
});
