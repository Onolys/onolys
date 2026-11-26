import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { CHART_COLORS, winShareTint } from './theme';

const lum = (rgb: number[]) => { const [r, g, b] = rgb.map(v => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const contrast = (a: number[], b: number[]) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
const parse = (c: string) => (c.startsWith('#') ? [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)) : c.match(/\d+/g)!.map(Number));
const cssFile = '../../compare/charts/matrix.css'; // variable so Vite does not rewrite new URL()
const css = readFileSync(new URL(cssFile, import.meta.url), 'utf8');

it('tinted-cell sub-label uses the foreground colour and stays >= 4.5:1 at shares 0, 0.5, 1', () => {
 expect(css).toMatch(/\.mx-cell \.mx-sub\s*\{[^}]*color:\s*var\(--foreground,\s*#171c1c\)/);
 expect(CHART_COLORS.ink).toBe('#171c1c');
 for (const share of [0, 0.5, 1]) expect(contrast(parse(CHART_COLORS.ink), parse(winShareTint(share))), `share ${share}`).toBeGreaterThanOrEqual(4.5);
});
