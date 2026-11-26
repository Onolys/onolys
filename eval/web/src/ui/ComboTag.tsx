import { comboColor, comboLetter, comboShape, type ComboShape } from "./chart/theme";
import "./ui.css";

const SHAPES: Record<ComboShape, string> = {
  circle: "M6 1a5 5 0 1 0 0 10A5 5 0 0 0 6 1Z",
  square: "M2 2h8v8H2Z",
  triangle: "M6 1.5 11 10.5H1Z",
  diamond: "M6 1 11 6 6 11 1 6Z",
  cross: "M4.5 1h3v3.5H11v3H7.5V11h-3V7.5H1v-3h3.5Z",
  star: "M6 1l1.5 3.3 3.5.4-2.6 2.4.7 3.6L6 8.9 2.9 10.7l.7-3.6L1 4.7l3.5-.4Z",
  hexagon: "M6 1l4.3 2.5v5L6 11 1.7 8.5v-5Z",
};

/** Combo identity: letter + shape + colour (never colour alone). `index` picks all three; `letter` overrides the letter only. */
export function ComboTag({ index, letter }: { index: number; letter?: string }) {
  const shape = comboShape(index);
  const text = letter ?? comboLetter(index);
  return <span className="ui-combo-tag" role="img" style={{ color: comboColor(index) }} aria-label={`Combo ${text}`}>
    <svg viewBox="0 0 12 12" aria-hidden="true" data-shape={shape}><path d={SHAPES[shape]} fill="currentColor" /></svg>
    <span aria-hidden="true">{text}</span>
  </span>;
}
