/** Chart theme: light mode only. Values mirror the mockup tokens (mockups/lib.js) and `@onolys/common`. */
export const CHART_COLORS = {
  ink: "#171c1c",
  muted: "#536160",
  grid: "#d3dbda",
  axis: "#6e7e7c",
  primary: "#0b5f5a",
  good: "#175b42",
  fair: "#71500a",
  low: "#8a3030",
  info: "#1d4f91",
} as const;

/** Fixed margins so tick labels never clip or overlap the plot: the left gutter always fits "1"-"5" or short labels. */
export const CHART_GUTTER = { top: 12, right: 16, bottom: 32, left: 56 } as const;

/** Inner plot box inside an outer width/height after the fixed gutter. */
export function plotBox(width: number, height: number, gutter: { top: number; right: number; bottom: number; left: number } = CHART_GUTTER) {
  return { left: gutter.left, top: gutter.top, width: Math.max(0, width - gutter.left - gutter.right), height: Math.max(0, height - gutter.top - gutter.bottom) };
}

/** Combo identity colours A, B, C, D, E, F, G (colour-blind-safe set; always paired with a letter and a shape). */
export const COMBO_PALETTE = ["#0b5f5a", "#b45309", "#1d4f91", "#7a3f98", "#a3185f", "#4d7c0f", "#0e7490"] as const;
export const COMBO_SHAPES = ["circle", "square", "triangle", "diamond", "cross", "star", "hexagon"] as const;
export type ComboShape = (typeof COMBO_SHAPES)[number];
/** Human reference series (not a combo). */
export const HUMAN_COLOR = "#171c1c";

export const comboColor = (index: number) => COMBO_PALETTE[index % COMBO_PALETTE.length];
export const comboShape = (index: number): ComboShape => COMBO_SHAPES[index % COMBO_SHAPES.length];
export const comboLetter = (index: number) => String.fromCharCode(65 + (index % 26));

const hex = (c: string) => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
/** Diverging tint for a win share in [0,1]: white at 0.5, towards `low` red below and `good` green above (max 55% mix so text stays readable). */
export function winShareTint(share: number): string {
  const s = Math.min(1, Math.max(0, share));
  const [r, g, b] = hex(s >= 0.5 ? CHART_COLORS.good : CHART_COLORS.low);
  const k = Math.abs(s - 0.5) * 2 * 0.55;
  const mix = (c: number) => Math.round(255 + (c - 255) * k);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}
