import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { drinkingSampleNotCoded, drinkingSampleReport, drinkingSampleTurns } from "../../mocks/fixtures/sample";
import { formatDate } from "../../lib/format";
import { ReportView } from "./ReportView";

const ready = { status: "ready" as const, turns: drinkingSampleTurns };

const scroll = vi.fn();
beforeEach(() => {
  scroll.mockClear();
  Element.prototype.scrollIntoView = scroll as unknown as typeof Element.prototype.scrollIntoView;
});

function view(props: Partial<React.ComponentProps<typeof ReportView>> = {}) {
  return render(
    <ReportView
      report={drinkingSampleReport}
      turns={ready}
      title="Sample report"
      headerSlot={<p className="sub">Example report from a made-up role-play conversation.</p>}
      notCoded={drinkingSampleNotCoded}
      {...props}
    />,
  );
}

const dlg = () => document.querySelector("dialog") as HTMLDialogElement;

const rowOf = (name: string) => screen.getByRole("row", { name: new RegExp(`^${name}\\b`) });

describe("ReportView", () => {
  it("renders the sections in fixed order and none of the old parts", () => {
    view();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Sample report");
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "At a glance",
      "Feedback: ideas to try",
      "Behaviour counts",
      "Coded transcript",
      "Method & limits",
    ]);
    expect(screen.getByText("Example report from a made-up role-play conversation.")).toBeTruthy();
    expect(screen.queryByText(/Scorecard/i)).toBeNull();
    expect(screen.queryByText(/Where Onolys disagrees/i)).toBeNull();
    expect(screen.queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("shows header goal and meta", () => {
    view();
    expect(screen.getByText("Cut down on drinking")).toBeTruthy();
    expect(screen.getByText("MITI 4.2.1")).toBeTruthy();
    expect(screen.getByText("Full conversation (54 utterances)")).toBeTruthy();
    expect(screen.getByText(formatDate("2026-11-20T09:30:00.000Z"))).toBeTruthy();
  });

  it("shows the four globals with value and reason", () => {
    view();
    const items = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-global"));
    expect(items).toHaveLength(4);
    expect(items.map((li) => within(li).getByRole("img").getAttribute("aria-label"))).toEqual([
      "2 out of 5",
      "2 out of 5",
      "2 out of 5",
      "3 out of 5",
    ]);
    expect(items[0].textContent).toContain("The client gives reasons to act");
  });

  it("renders all evidence inline as bracketed citations and opens the matching row", () => {
    view();
    const cct = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-global"))[0];
    expect(cct.textContent).not.toContain("Evidence:");
    expect(within(cct).getAllByRole("button").map((b) => b.textContent)).toEqual(["[18]", "[19]", "[31]", "[40]", "[41]"]);
    fireEvent.click(within(cct).getByRole("button", { name: "Open utterance 31" }));
    expect(dlg().hasAttribute("open")).toBe(true);
    expect(scroll.mock.instances[0]).toBe(document.getElementById("utt-31"));
  });

  it("converts verified internal IDs without inferring utterance numbers from their suffix", () => {
    const r = structuredClone(drinkingSampleReport);
    r.globals![0].onolys.reason = "The response at t40 builds on change talk; t999 is unavailable.";
    const turns = [...drinkingSampleTurns];
    [turns[17], turns[39]] = [turns[39], turns[17]];
    view({ report: r, turns: { status: "ready", turns } });
    const cct = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-global"))[0];
    expect(cct.textContent).toContain("The response at [18] builds on change talk");
    expect(cct.textContent).not.toMatch(/t40|t999/);
    expect(within(cct).getAllByRole("button").map((b) => b.textContent)).not.toContain("[999]");
  });

  it("keeps ordinary prose intact when arbitrary transcript IDs look like words or scores", () => {
    const r = structuredClone(drinkingSampleReport);
    r.globals![0].onolys.reason = "The client gives 3 reasons to act.";
    const turns = drinkingSampleTurns.map((t, i) => ({ ...t, id: i === 0 ? "The" : i === 1 ? "3" : t.id }));
    view({ report: r, turns: { status: "ready", turns } });
    const cct = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-global"))[0];
    expect(cct.textContent).toContain("The client gives 3 reasons to act.");
  });

  it("uses a neutral code label when an older tip has no idea title", () => {
    const r = structuredClone(drinkingSampleReport);
    delete r.tips![0].title;
    view({ report: r });
    expect(screen.getByRole("heading", { name: "Confront: an idea to try" })).toBeInTheDocument();
  });

  it("uses the generated idea title and preserves the original observation verbatim", () => {
    const r = structuredClone(drinkingSampleReport);
    r.tips![0].title = "Reflect the client's aim first";
    r.tips![0].observation = "Onolys reads this as MI advice offered early.";
    view({ report: r });
    expect(screen.getByRole("heading", { name: "Reflect the client's aim first" })).toBeInTheDocument();
    expect(screen.getByText("Onolys reads this as MI advice offered early.")).toBeInTheDocument();
  });

  it("omits evidence links while the transcript is unavailable", () => {
    const { container } = view({ turns: { status: "loading" } });
    expect(container.querySelector("#glance button")).toBeNull();
  });

  it("renders the summary table with chips, and No reference level for null references", () => {
    view();
    const t = screen.getByRole("table", { name: "Summary scores" });
    const rows = within(t).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(6);
    const cells = rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent));
    expect(cells[0].slice(1)).toEqual(["2.0", "3.0", "4.0", "Below fair"]);
    expect(cells[1].slice(1)).toEqual(["2.5", "3.5", "4.0", "Below fair"]);
    expect(cells[2].slice(1)).toEqual(["58%", "40%", "50%", "Good"]);
    expect(cells[3].slice(1)).toEqual(["1.7", "1.0", "2.0", "Fair"]);
    expect(cells[4].slice(1)).toEqual(["6", "–", "–", "No reference level"]);
    expect(cells[5].slice(1)).toEqual(["2", "–", "–", "No reference level"]);
    expect(within(rows[4]).queryByText(/Fair|Good|Below/)).toBeNull();
    expect(screen.getByText("Fair and good are reference levels, not pass marks.")).toBeTruthy();
  });

  it("renders ranked tip cards with quote, utterance link, alternative and why", () => {
    view();
    const tips = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-tip"));
    expect(tips).toHaveLength(3);
    expect(within(tips[0]).getByRole("heading", { level: 3 })).toBeInTheDocument();
    expect(tips[0].textContent).toContain("Arguing against cutting down closed the client off");
    expect(within(tips[0]).getByText("Confront")).toBeTruthy();
    expect(within(tips[0]).getByText("What was said")).toBeTruthy();
    expect(within(tips[0]).getByText("Try instead")).toBeTruthy();
    expect(within(tips[0]).getByText("Why it matters")).toBeTruthy();
    expect(tips[0].querySelector("[data-try] [data-eg]")!.textContent).toContain("You'd like to keep wine in your life");
    fireEvent.click(within(tips[0]).getByRole("button", { name: "Open utterance 25" }));
    expect(dlg().hasAttribute("open")).toBe(true);
    expect(scroll.mock.instances[0]).toBe(document.getElementById("utt-25"));
  });

  it("hides Feedback when there are no tips, but shows a warning notice", () => {
    const none = { ...drinkingSampleReport, tips: [], warnings: [] };
    const { unmount } = view({ report: none });
    expect(screen.queryByRole("heading", { name: /Feedback/ })).toBeNull();
    unmount();
    view({ report: { ...none, warnings: [{ code: "tips_failed" }] } });
    expect(screen.getByRole("heading", { name: /Feedback/ })).toBeTruthy();
    expect(screen.getByText("We couldn't write tips this time.")).toBeTruthy();
  });

  it("totals are round(sum of unrounded means), not the sum of rounded rows", () => {
    const r = structuredClone(drinkingSampleReport);
    const mean = (id: string, v: number) => {
      r.behaviours!.find((b) => b.item_id === id)!.onolys_count.mean = v;
    };
    mean("affirm", 1.5);
    mean("seek_collab", 1.5);
    mean("emphasize_autonomy", 0);
    view({ report: r });
    const t = screen.getByRole("table", { name: "Behaviour counts" });
    const cellOf = (label: string) => {
      const row = within(t).getAllByRole("row").find((tr) => within(tr).queryAllByRole("cell")[1]?.textContent === label)!;
      return within(row).getAllByRole("cell").at(-1)!.textContent;
    };
    expect(cellOf("Affirm")).toBe("2");
    expect(cellOf("Seek Collaboration")).toBe("2");
    expect(cellOf("Emphasize Autonomy")).toBe("0");
    expect(cellOf("Total MI-adherent")).toBe("3");
  });

  it("builds the coded rows once: the section count and the dialog count agree", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: "Open coded transcript" }));
    expect(within(dlg()).getByText(/54 utterances, 27 from the practitioner/)).toBeTruthy();
    expect(document.querySelectorAll("dialog")).toHaveLength(1);
  });

  it("shows counts and totals from the sample, rounding the mean", () => {
    const r = structuredClone(drinkingSampleReport);
    r.behaviours!.find((b) => b.item_id === "gi")!.onolys_count.mean = 1.6;
    view({ report: r });
    const t = screen.getByRole("table", { name: "Behaviour counts" });
    const count = (label: string) => {
      const row = within(t).getAllByRole("row").find((tr) => within(tr).queryAllByRole("cell")[1]?.textContent === label)!;
      return within(row).getAllByRole("cell").at(-1)!.textContent;
    };
    expect(count("Giving Information")).toBe("2");
    expect(count("Persuade")).toBe("1");
    expect(count("Persuade with Permission")).toBe("3");
    expect(count("Question")).toBe("7");
    expect(count("Simple Reflection")).toBe("5");
    expect(count("Complex Reflection")).toBe("7");
    expect(count("Affirm")).toBe("2");
    expect(count("Seek Collaboration")).toBe("2");
    expect(count("Emphasize Autonomy")).toBe("2");
    expect(count("Confront")).toBe("1");
    expect(count("Total MI-adherent")).toBe("6");
    expect(count("Total MI non-adherent (Confront + Persuade)")).toBe("2");
    expect(rowOf("Information & persuasion")).toBeTruthy();
  });

  it("shows the transcript count line and button; disabled while loading", () => {
    const { unmount } = view();
    expect(screen.getAllByText("54 utterances, 27 from the practitioner. Each code shows the reason it was given.")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Open coded transcript" }));
    expect(dlg().hasAttribute("open")).toBe(true);
    expect(scroll).not.toHaveBeenCalled();
    unmount();
    view({ turns: { status: "loading" } });
    const b = screen.getByRole("button", { name: "Loading transcript…" }) as HTMLButtonElement;
    expect(b.disabled).toBe(true);
  });

  it("shows a transcript error with Try again when a retry is given", () => {
    const retry = vi.fn();
    view({ turns: { status: "error", retry } });
    expect(screen.getAllByText("We couldn't load the transcript.")).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "Try again" })[0]);
    expect(retry).toHaveBeenCalled();
  });

  it("renders method, limits, citation and the not-official note", () => {
    view();
    expect(screen.getByText(/Onolys reads the transcript against the MITI 4.2.1/)).toBeTruthy();
    expect(screen.getByText(/Tone of voice, pauses/)).toBeTruthy();
    expect(screen.getByText(/Moyers, T. B./)).toBeTruthy();
    expect(screen.getByText("Not official MITI coding and cannot be submitted as one.")).toBeTruthy();
  });

  it("emits no inline style attribute", () => {
    const { container } = view();
    expect(container.innerHTML).not.toMatch(/style=/);
  });
});

describe("ReportView follow-ups (C14, C15, warnings)", () => {
  it("formats the header date with the shared formatter (user's locale and zone)", async () => {
    view();
    expect(screen.getByText(formatDate("2026-11-20T09:30:00.000Z"))).toBeTruthy();
    expect(screen.queryByText("20 Nov 2026")).toBeNull();
  });

  it("shows a dash labelled 'no data' (not 0) when a behaviour has no onolys_count, and no total from nothing", () => {
    const r = structuredClone(drinkingSampleReport);
    delete (r.behaviours!.find((b) => b.item_id === "confront") as { onolys_count?: unknown }).onolys_count;
    view({ report: r });
    const t = screen.getByRole("table", { name: "Behaviour counts" });
    const row = within(t).getAllByRole("row").find((tr) => within(tr).queryAllByRole("cell")[1]?.textContent === "Confront")!;
    const cell = within(row).getAllByRole("cell").at(-1)!;
    expect(cell.textContent).toBe("–");
    expect(within(cell).getByRole("img", { name: "no data" })).toBeTruthy();
  });

  it("explains per-run engine codes in plain language, once each", () => {
    const codes = ["quote_not_found", "overlap", "insufficient_evidence", "capped", "reason_withheld_tone"];
    const r = { ...drinkingSampleReport, warnings: [...codes, "quote_not_found", "reason_withheld_tone"].map((code) => ({ code, item_id: "gi" })) };
    view({ report: r });
    const notes = screen.getAllByRole("note");
    expect(notes).toHaveLength(codes.length);
    for (const n of notes) expect(n.textContent).not.toMatch(/_|processing note/);
  });

  it("shows an unknown warning code as a generic note instead of hiding it (once)", () => {
    const r = { ...drinkingSampleReport, warnings: [{ code: "brand_new_code" }, { code: "another_new_code" }] };
    view({ report: r });
    const notes = screen.getAllByRole("note");
    expect(notes).toHaveLength(1);
    expect(notes[0]!.textContent).toBe("Some parts of this report had a processing note.");
  });

  it("shows each applicable sample warning once", async () => {
    view();
    expect(screen.getAllByRole("note").map((n) => n.textContent)).toEqual([
      "This session is shorter than 10 minutes, so global ratings may be harder to judge.",
      "The practitioner speaks first in this excerpt. Opening reflections have no earlier client speech here to refer to.",
    ]);
  });
});
