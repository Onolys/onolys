import type { ReactNode } from "react";
import "./ui.css";

export const isZero = (v: ReactNode) => v === 0 || v === "0";

/** Compact key/value tile: small caps label, bold value, optional muted sub. Zero values render muted. */
export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return <div className="ui-stat">
    <span className="ui-stat-label">{label}</span>
    <span className={`ui-stat-value${isZero(value) ? " ui-zero" : ""}`}>{value}</span>
    {sub != null && <span className="ui-stat-sub">{sub}</span>}
  </div>;
}
