import { AxisBottom, AxisLeft } from "@visx/axis";
import type { AxisScale } from "@visx/axis";
import { CHART_COLORS, CHART_GUTTER } from "./theme";

const plain = (v: number) => String(Number(v.toFixed(2)));
const TICK_LABEL = { fill: CHART_COLORS.muted, fontSize: 12, fontFamily: "inherit" } as const;

/** Chart axis on a fixed gutter: the left axis sits at `left` (default CHART_GUTTER.left) so labels never clip. */
export function Axis({ orientation, scale, tickValues, top = 0, left = orientation === "left" ? CHART_GUTTER.left : 0, label, numTicks, tickFormat }: {
  orientation: "left" | "bottom";
  scale: AxisScale<number>;
  tickValues?: number[];
  top?: number;
  left?: number;
  label?: string;
  numTicks?: number;
  tickFormat?: (v: number) => string;
}) {
  const common = {
    scale,
    top,
    left,
    tickValues,
    numTicks,
    label,
    tickFormat: (v: { valueOf(): number }) => (tickFormat ?? plain)(v.valueOf()),
    stroke: CHART_COLORS.axis,
    tickStroke: CHART_COLORS.axis,
    labelProps: { ...TICK_LABEL, textAnchor: "middle" as const },
    tickLabelProps: () => ({ ...TICK_LABEL, textAnchor: orientation === "left" ? ("end" as const) : ("middle" as const), dy: orientation === "left" ? "0.33em" : undefined }),
  };
  return <g className="ui-axis">{orientation === "left" ? <AxisLeft {...common} /> : <AxisBottom {...common} />}</g>;
}
