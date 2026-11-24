import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  drinkingSampleNotCoded,
  drinkingSampleReport,
  drinkingSampleTurns,
} from "../../mocks/fixtures/sample";
import { ReportView, type TurnsState } from "./ReportView";

const ready: TurnsState = { status: "ready", turns: drinkingSampleTurns };

function view(
  turns: TurnsState = ready,
  notCoded: ReadonlySet<string> | undefined = drinkingSampleNotCoded,
) {
  return render(
    <ReportView
      report={drinkingSampleReport}
      turns={turns}
      notCoded={notCoded}
    />,
  );
}

const dlg = () => document.querySelector("dialog") as HTMLDialogElement;
const html = () => document.documentElement;

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  html().classList.remove("dlg-open");
});

describe("CodedTranscriptDialog", () => {
  it("is closed until opened, then opens as a modal with an accessible name", () => {
    view();
    expect(dlg().hasAttribute("open")).toBe(false);
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    expect(dlg().hasAttribute("open")).toBe(true);
    const d = screen.getByRole("dialog", { name: "Coded transcript" });
    expect(
      within(d).getByText(/54 utterances, 27 from the practitioner/),
    ).toBeTruthy();
  });

  it("highlights a cited utterance for five seconds and clears it on close", () => {
    vi.useFakeTimers();
    view();
    fireEvent.click(screen.getAllByRole("button", { name: "Open utterance 31" })[0]);
    const row = document.getElementById("utt-31")!;
    expect(row).toHaveClass("hl");
    act(() => vi.advanceTimersByTime(4900));
    expect(row).toHaveClass("hl");
    act(() => vi.advanceTimersByTime(100));
    expect(row).not.toHaveClass("hl");
    fireEvent.click(within(dlg()).getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Open utterance 31" })[0]);
    expect(row).toHaveClass("hl");
    fireEvent.click(within(dlg()).getByRole("button", { name: "Close" }));
    expect(row).not.toHaveClass("hl");
  });

  it("locks body scroll with a class on <html> while open and clears it on close", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    expect(html().classList.contains("dlg-open")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(dlg().hasAttribute("open")).toBe(false);
    expect(html().classList.contains("dlg-open")).toBe(false);
  });

  it("closes on Escape (native cancel then close) and returns focus to the opener", () => {
    view();
    const opener = screen.getByRole("button", {
      name: "Open coded transcript",
    });
    opener.focus();
    fireEvent.click(opener);
    // What the browser does on Esc: fire cancel, then close the dialog.
    act(() => {
      const ev = new Event("cancel", { cancelable: true });
      dlg().dispatchEvent(ev);
      if (!ev.defaultPrevented) dlg().close();
    });
    expect(dlg().hasAttribute("open")).toBe(false);
    expect(html().classList.contains("dlg-open")).toBe(false);
    expect(document.activeElement).toBe(opener);
  });

  it("closes on backdrop click but not on a click inside", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    fireEvent.click(screen.getByText("Utt #"));
    expect(dlg().hasAttribute("open")).toBe(true);
    fireEvent.mouseDown(dlg());
    fireEvent.click(dlg());
    expect(dlg().hasAttribute("open")).toBe(false);
  });

  it("does not close when the press started inside the dialog and the click ends on the backdrop", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    // Text-drag: mousedown on content, release (click) on the <dialog> backdrop.
    fireEvent.mouseDown(screen.getByText("Utt #"));
    fireEvent.click(dlg());
    expect(dlg().hasAttribute("open")).toBe(true);
    // The next full backdrop click still closes it.
    fireEvent.mouseDown(dlg());
    fireEvent.click(dlg());
    expect(dlg().hasAttribute("open")).toBe(false);
  });

  it("ignores a click on the dialog with no mousedown on it", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    fireEvent.click(dlg());
    expect(dlg().hasAttribute("open")).toBe(true);
  });

  it("returns focus to the Close-button path opener too", () => {
    view();
    const opener = screen.getByRole("button", {
      name: "Open coded transcript",
    });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(document.activeElement).toBe(opener);
  });

  it("renders the table with the five columns, row ids utt-N, and a legend from report codes", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    const heads = within(dlg())
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(heads).toEqual(["Utt #", "Speaker", "Utterance", "Code(s)", "Why"]);
    expect(dlg().querySelector("#utt-1")).toBeTruthy();
    expect(dlg().querySelector("#utt-54")).toBeTruthy();
    const legend = dlg().querySelector("details[data-legend]")!;
    expect(legend.querySelector("summary")!.textContent).toBe("Code legend");
    expect(legend.textContent).toContain("Emphasize Autonomy");
    expect(legend.textContent).toContain("Persuade with Permission");
    expect(legend.textContent).toContain("Not coded");
  });

  it("shows both chips and both rationales on multi-code row 29", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    const row = dlg().querySelector("#utt-29")!;
    expect(
      [...row.querySelectorAll("[data-code]")].map((c) => c.textContent),
    ).toEqual(["EA", "PwP"]);
    expect(row.textContent).toContain("'your call'");
    expect(row.textContent).toContain(
      "Persuade with permission because client asked",
    );
  });

  it("shows 'Not coded' on turn 53 in sample mode and an em dash in real mode", () => {
    const { unmount } = view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    expect(dlg().querySelector("#utt-53")!.textContent).toContain("Not coded");
    unmount();
    view(ready, new Set());
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    const row = dlg().querySelector("#utt-53")!;
    expect(row.textContent).not.toContain("Not coded");
    expect(row.textContent).toContain("—");
  });

  it("client rows show no code and no dash", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    const cells = dlg().querySelectorAll("#utt-2 td");
    expect(cells[3].textContent).toBe("");
    expect(cells[4].textContent).toBe("");
  });

  it("has no inline style attributes (CSP)", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    expect(dlg().innerHTML).not.toMatch(/style="/);
  });

  it("on a transcript error shows the message with Try again, which calls retry", () => {
    const retry = vi.fn();
    view({ status: "error", retry });
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    const d = screen.getByRole("dialog", { name: "Coded transcript" });
    expect(
      within(d).getByText("We couldn't load the transcript."),
    ).toBeTruthy();
    fireEvent.click(within(d).getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
    expect(d.querySelector("table")).toBeNull();
  });

  it("mounts a single dialog and shows no utterance links while the transcript errored", () => {
    view({ status: "error" });
    expect(document.querySelectorAll("dialog")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /^Open utterance/ })).toBeNull();
  });

  it("lists chips and rationales in text order on the multi-code rows (mockup order)", () => {
    view();
    fireEvent.click(
      screen.getByRole("button", { name: "Open coded transcript" }),
    );
    const order: Record<number, string[]> = {
      29: ["EA", "PwP"],
      33: ["EA", "Q"],
      35: ["AF", "Q"],
      39: ["GI", "Q"],
      49: ["AF", "Seek"],
    };
    for (const [n, chips] of Object.entries(order)) {
      const row = dlg().querySelector(`#utt-${n}`)!;
      expect(
        [...row.querySelectorAll("[data-codes] [data-code]")].map((c) => c.textContent),
      ).toEqual(chips);
      const why = [...row.querySelectorAll("td:last-child > div")].map(
        (d) => d.textContent!.split(":")[0],
      );
      expect(why).toEqual(chips);
    }
  });
});

describe("CodedTranscriptDialog on narrow screens (C18)", () => {
  it("stacks each row below 640px so the Why text is never cut off, and labels every cell", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: "Open coded transcript" }));
    const d = dlg();
    const table = d.querySelector("table")!;
    expect(table.className).toMatch(/max-\[640px\]:block/);
    const row = d.querySelector("#utt-25")!;
    expect(row.className).toMatch(/max-\[640px\]:block/);
    const cells = [...row.querySelectorAll("td")];
    expect(cells.map((c) => c.getAttribute("data-label"))).toEqual(["Utt #", "Speaker", "Utterance", "Code(s)", "Why"]);
    for (const c of cells) expect(c.className).toMatch(/max-\[640px\]:block/);
    expect(cells[4]!.className).toMatch(/max-\[640px\]:before:/);
  });
});
