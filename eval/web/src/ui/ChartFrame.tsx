import { useId, type ReactNode } from "react";
import { Disclosure } from "./Disclosure";
import "./ui.css";

/** Chart card: title, one-sentence caption, optional legend, the chart, and the table twin behind a collapsed "Show data" disclosure. */
export function ChartFrame({ title, caption, legend, table, showDataLabel = "Show data", children }: { title: string; caption: string; legend?: ReactNode; table: ReactNode; showDataLabel?: string; children: ReactNode }) {
  const id = useId();
  return <section className="ui-chart-frame" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`} className="ui-chart-title">{title}</h3>
    <p id={`${id}-caption`} className="ui-chart-caption">{caption}</p>
    {legend ? <div className="ui-chart-legend">{legend}</div> : null}
    <div className="ui-chart-body" aria-describedby={`${id}-caption`}>{children}</div>
    <Disclosure label={showDataLabel}><div className="ui-chart-data" role="group" aria-label={`${title} data`}>{table}</div></Disclosure>
  </section>;
}
