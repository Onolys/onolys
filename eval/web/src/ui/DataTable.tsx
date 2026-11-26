import { ArrowDown, ArrowUp, Search } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useTableState, type Cell, type SortDir } from "./useTableState";
import "./ui.css";

export type RowTone = "danger" | "warning" | "success";
export type Column<T> = {
  key: string;
  header: string;
  /** Required plain value: used for sorting, search and the full-value tooltip, even when `render` is given. */
  value: (row: T) => Cell;
  /** Custom cell content; falls back to `value`. */
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  /** "low" columns are hidden at medium widths so the table never needs a horizontal scrollbar. */
  priority?: "low";
  /** Optional CSS width for the column (fixed layout), e.g. "16%". */
  width?: string;
};

const ariaSort = (dir: SortDir | undefined) => (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none");

/** Fixed-layout, searchable, sortable table. Headers are plain th (no buttons); no horizontal scroll: cells wrap/ellipsize with a title, low-priority columns hide, and below 760px rows stack into cards. */
export function DataTable<T>({ rows, columns, rowKey, rowTone, filters, searchLabel = "Search", empty = "No matching rows.", ariaLabel }: {
  rows: readonly T[]; columns: readonly Column<T>[]; rowKey: (row: T) => string;
  rowTone?: (row: T) => RowTone | undefined; filters?: ReactNode | ((ctl: { setFilter: (fn: ((row: T) => boolean) | null) => void }) => ReactNode); searchLabel?: string; empty?: string; ariaLabel?: string;
}) {
  const { visible, search, setSearch, sort, toggleSort, setFilter } = useTableState(rows, columns);
  const onKey = (key: string) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSort(key); }
  };
  return <div className="ui-table-wrap">
    <div className="ui-table-toolbar">
      <label className="ui-table-search"><Search aria-hidden="true" />
        <input type="search" value={search} placeholder={searchLabel} aria-label={searchLabel} onChange={(e) => setSearch(e.target.value)} />
      </label>
      {filters ? <div className="ui-table-filters">{typeof filters === "function" ? filters({ setFilter }) : filters}</div> : null}
    </div>
    <table className="ui-table" aria-label={ariaLabel}>
      <thead><tr>
        {columns.map((c) => {
          const sortable = c.sortable !== false;
          const dir = sort?.key === c.key ? sort.dir : undefined;
          return <th key={c.key} scope="col" style={c.width ? { width: c.width } : undefined} className={`${c.priority === "low" ? "ui-col-low " : ""}${sortable ? "ui-th-sortable" : ""}`}
            aria-sort={sortable ? ariaSort(dir) : undefined} tabIndex={sortable ? 0 : undefined}
            onClick={sortable ? () => toggleSort(c.key) : undefined} onKeyDown={sortable ? onKey(c.key) : undefined}>
            <span className="ui-th-label">{c.header}</span>
            {sortable ? <span className="ui-sort" aria-hidden="true">
              <ArrowUp className={dir === "asc" ? "is-active" : ""} /><ArrowDown className={dir === "desc" ? "is-active" : ""} />
            </span> : null}
          </th>;
        })}
      </tr></thead>
      <tbody>
        {visible.map((row) => {
          const tone = rowTone?.(row);
          return <tr key={rowKey(row)} className={tone ? `ui-row-${tone}` : undefined}>
            {columns.map((c) => {
              const v = c.value(row);
              const title = v == null || v === "" ? undefined : String(v);
              return <td key={c.key} data-label={c.header} title={title} className={c.priority === "low" ? "ui-col-low" : undefined}>
                <span className="ui-cell">{c.render ? c.render(row) : v}</span>
              </td>;
            })}
          </tr>;
        })}
        {visible.length === 0 ? <tr className="ui-table-empty"><td colSpan={columns.length}>{empty}</td></tr> : null}
      </tbody>
    </table>
  </div>;
}
