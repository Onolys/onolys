// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { DataTable, type Column } from "./DataTable";
import { useTableState } from "./useTableState";

afterEach(cleanup);

type Row = { id: string; name: string; score: number | null; status: string };
const rows: Row[] = [
  { id: "a", name: "Charlie", score: 2, status: "ok" },
  { id: "b", name: "alpha", score: 10, status: "failed" },
  { id: "c", name: "Bravo", score: null, status: "ok" },
];
const columns: Column<Row>[] = [
  { key: "name", header: "Name", value: (r) => r.name },
  { key: "score", header: "Score", value: (r) => r.score },
  { key: "status", header: "Status", value: (r) => r.status, priority: "low" },
  { key: "static", header: "Static", sortable: false, render: () => "x" },
];
const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);

it("every sortable column cycles asc -> desc -> none with aria-sort", () => {
  render(<DataTable rows={rows} columns={columns} rowKey={(r) => r.id} />);
  for (const [key, header] of [["name", "Name"], ["score", "Score"], ["status", "Status"]]) {
    const th = screen.getByRole("columnheader", { name: header });
    expect(th.getAttribute("aria-sort"), key).toBe("none");
    fireEvent.click(th);
    expect(th.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(th);
    expect(th.getAttribute("aria-sort")).toBe("descending");
    fireEvent.click(th);
    expect(th.getAttribute("aria-sort")).toBe("none");
  }
  expect(screen.getByRole("columnheader", { name: "Static" }).hasAttribute("aria-sort")).toBe(false);
});

it("sorts rows (case-insensitive text, numbers numerically, nulls last) and restores original order", () => {
  render(<DataTable rows={rows} columns={columns} rowKey={(r) => r.id} />);
  expect(names()).toEqual(["Charlie", "alpha", "Bravo"]);
  fireEvent.click(screen.getByRole("columnheader", { name: "Name" }));
  expect(names()).toEqual(["alpha", "Bravo", "Charlie"]);
  fireEvent.click(screen.getByRole("columnheader", { name: "Name" }));
  expect(names()).toEqual(["Charlie", "Bravo", "alpha"]);
  fireEvent.click(screen.getByRole("columnheader", { name: "Name" }));
  fireEvent.click(screen.getByRole("columnheader", { name: "Score" }));
  expect(names()).toEqual(["Charlie", "alpha", "Bravo"]);
  fireEvent.click(screen.getByRole("columnheader", { name: "Score" }));
  expect(names()).toEqual(["alpha", "Charlie", "Bravo"]);
});

it("th is keyboard operable via Enter/Space and contains no button; shows up and down arrows", () => {
  const { container } = render(<DataTable rows={rows} columns={columns} rowKey={(r) => r.id} />);
  const th = screen.getByRole("columnheader", { name: "Name" });
  expect(container.querySelector("thead button")).toBeNull();
  expect(th.tabIndex).toBe(0);
  expect(th.querySelectorAll("svg").length).toBe(2);
  fireEvent.keyDown(th, { key: "Enter" });
  expect(th.getAttribute("aria-sort")).toBe("ascending");
  fireEvent.keyDown(th, { key: " " });
  expect(th.getAttribute("aria-sort")).toBe("descending");
});

it("search filters rows and shows an empty state", () => {
  render(<DataTable rows={rows} columns={columns} rowKey={(r) => r.id} />);
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "brav" } });
  expect(names()).toEqual(["Bravo"]);
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzz" } });
  expect(screen.getByText(/no matching rows/i)).toBeTruthy();
});

it("filter slot renders in the toolbar", () => {
  render(<DataTable rows={rows} columns={columns} rowKey={(r) => r.id} filters={<span>FilterSlot</span>} />);
  expect(screen.getByText("FilterSlot")).toBeTruthy();
});

it("long cell has a title with the full value, fixed layout, low-priority column class, and danger row tone", () => {
  const long = "x".repeat(200);
  const { container } = render(<DataTable rows={[{ id: "z", name: long, score: 1, status: "failed" }]} columns={columns} rowKey={(r) => r.id} rowTone={(r) => (r.status === "failed" ? "danger" : undefined)} />);
  expect(screen.getByTitle(long)).toBeTruthy();
  expect(container.querySelector("table")!.classList.contains("ui-table")).toBe(true);
  expect(container.querySelector("tbody tr")!.classList.contains("ui-row-danger")).toBe(true);
  expect(container.querySelector("th.ui-col-low")).toBeTruthy();
  expect(container.querySelector("td[data-label='Name']")).toBeTruthy();
});

it("useTableState: sort cycle, search and filter", () => {
  const { result } = renderHook(() => useTableState(rows, columns));
  expect(result.current.visible).toHaveLength(3);
  act(() => result.current.toggleSort("score"));
  expect(result.current.sort).toEqual({ key: "score", dir: "asc" });
  act(() => result.current.setSearch("ok"));
  expect(result.current.visible.map((r) => r.id)).toEqual(["a", "c"]);
  act(() => result.current.setFilter(() => (r: Row) => r.id === "a"));
  expect(result.current.visible.map((r) => r.id)).toEqual(["a"]);
});
