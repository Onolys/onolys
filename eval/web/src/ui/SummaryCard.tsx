import type { ReactNode } from "react";
import { isZero } from "./StatTile";
import "./ui.css";

/** Summary card: small title, big value, muted sub-line. Zero values render muted. */
export function SummaryCard({ title, value, sub }: { title: string; value: ReactNode; sub?: ReactNode }) {
  return <div className="ui-summary">
    <span className="ui-summary-title">{title}</span>
    <span className={`ui-summary-value${isZero(value) ? " ui-zero" : ""}`}>{value}</span>
    {sub != null && <span className="ui-summary-sub">{sub}</span>}
  </div>;
}
