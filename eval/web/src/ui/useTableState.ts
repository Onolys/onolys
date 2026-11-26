import { useMemo, useState } from "react";

export type Cell = string | number | null | undefined;
export type SortDir = "asc" | "desc";
export type SortState = { key: string; dir: SortDir } | null;
export type SortableColumn<T> = { key: string; sortable?: boolean; value?: (row: T) => Cell };

const text = (v: Cell) => (v == null ? "" : String(v));

function compare(a: Cell, b: Cell): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return text(a).localeCompare(text(b), undefined, { numeric: true, sensitivity: "base" });
}

/** Search, filter and sort state for a table. Sort cycles asc -> desc -> none; null/empty values always sort last. */
export function useTableState<T>(rows: readonly T[], columns: readonly SortableColumn<T>[]) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortState>(null);
  const [filter, setFilter] = useState<((row: T) => boolean) | null>(null);

  const toggleSort = (key: string) => setSort((s) => (s?.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let out = rows.filter((r) => (!filter || filter(r)) && (!q || columns.some((c) => c.value && text(c.value(r)).toLowerCase().includes(q))));
    const col = sort && columns.find((c) => c.key === sort.key);
    if (sort && col?.value) {
      const get = col.value;
      const sign = sort.dir === "asc" ? 1 : -1;
      out = out.map((r, i) => ({ r, i })).sort((x, y) => {
        const a = get(x.r), b = get(y.r);
        const an = a == null || a === "", bn = b == null || b === "";
        if (an || bn) return an && bn ? x.i - y.i : an ? 1 : -1;
        return sign * compare(a, b) || x.i - y.i;
      }).map((e) => e.r);
    }
    return out;
  }, [rows, columns, search, sort, filter]);

  return { visible, search, setSearch, sort, toggleSort, filter, setFilter };
}
