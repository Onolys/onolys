/** Offsets from the engine are Unicode code points; JS strings index UTF-16 units (PRD D11). */

export function codePointLength(text: string): number {
  let n = 0;
  for (const _ of text) n++; // eslint-disable-line @typescript-eslint/no-unused-vars
  return n;
}

/** `map[cp]` = UTF-16 index of code point `cp`; length is codePointLength + 1 (last entry = text.length). */
export function buildIndexMap(text: string): number[] {
  const map: number[] = [];
  let unit = 0;
  for (const ch of text) {
    map.push(unit);
    unit += ch.length;
  }
  map.push(unit);
  return map;
}

/** Slice by code point, end exclusive. Negative, reversed or non-integer offsets give ""; `end` past the text is clamped. */
export function sliceCodePoints(text: string, start: number, end: number): string {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) return "";
  const map = buildIndexMap(text);
  if (start >= map.length) return "";
  return text.slice(map[start], map[Math.min(end, map.length - 1)]);
}
