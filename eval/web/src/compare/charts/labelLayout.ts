export interface LabelBox { id: string; x: number; y: number; w: number; h: number }
export interface LabelInput { id: string; px: number; py: number; w: number; h: number }
const overlaps = (a: LabelBox, b: LabelBox) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Place one label per point beside its marker; nudge labels (down, then up, then left of the marker) until none overlap each other or any marker. Pure geometry: no metric is computed. */
export function layoutLabels(points: LabelInput[], bounds: { left: number; top: number; right: number; bottom: number }, markerRadius = 8): LabelBox[] {
 const markers: LabelBox[] = points.map(p => ({ id: `m-${p.id}`, x: p.px - markerRadius, y: p.py - markerRadius, w: markerRadius * 2, h: markerRadius * 2 }));
 const placed: LabelBox[] = [];
 const clamp = (b: LabelBox): LabelBox => ({ ...b, x: Math.min(Math.max(b.x, bounds.left), Math.max(bounds.left, bounds.right - b.w)), y: Math.min(Math.max(b.y, bounds.top), Math.max(bounds.top, bounds.bottom - b.h)) });
 const clear = (b: LabelBox, own: string) => !placed.some(o => overlaps(b, o)) && !markers.some(m => m.id !== `m-${own}` && overlaps(b, m)) && !overlaps(b, markers.find(m => m.id === `m-${own}`)!);
 for (const p of [...points].sort((a, b) => a.py - b.py || a.px - b.px)) {
  const sides = [p.px + markerRadius + 2, p.px - markerRadius - 2 - p.w];
  let chosen: LabelBox | undefined;
  for (const x of sides) {
   for (let step = 0; step < 40 && !chosen; step++) {
    const dy = Math.ceil(step / 2) * (p.h + 1) * (step % 2 ? 1 : -1);
    const candidate = clamp({ id: p.id, x, y: p.py - p.h / 2 + dy, w: p.w, h: p.h });
    if (clear(candidate, p.id)) chosen = candidate;
   }
   if (chosen) break;
  }
  placed.push(chosen ?? clamp({ id: p.id, x: sides[0], y: p.py - p.h / 2, w: p.w, h: p.h }));
 }
 return points.map(p => placed.find(b => b.id === p.id)!);
}
