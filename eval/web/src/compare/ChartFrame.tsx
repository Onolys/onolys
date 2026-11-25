import { useId, type ReactNode } from 'react';
/** Every chart supplies its own semantic table, with a caption and row/column headers. */
export function ChartFrame({ title, howToRead, children, table }: { title:string; howToRead:string; children:ReactNode; table:ReactNode }) {
 const id=useId();
 return <section className="compare-chart" aria-labelledby={`${id}-title`}>
  <h3 id={`${id}-title`}>{title}</h3>
  <div aria-describedby={`${id}-caption`}>{children}</div>
  <p id={`${id}-caption`}><strong>How to read:</strong> {howToRead}</p>
  <details>
   <summary>Show data table for {title}</summary>
   {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll the table twin. */}
   <div className="table-scroll" role="region" aria-label={`${title} data`} tabIndex={0}>{table}</div>
  </details>
 </section>;
}
