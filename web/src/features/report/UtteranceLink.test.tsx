import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  drinkingSampleNotCoded,
  drinkingSampleReport,
  drinkingSampleTurns,
} from "../../mocks/fixtures/sample";
import { CodedTranscriptProvider } from "./CodedTranscriptDialog";
import { UtteranceLink } from "./UtteranceLink";

function view() {
  return render(
    <CodedTranscriptProvider
      report={drinkingSampleReport}
      turns={{ status: "ready", turns: drinkingSampleTurns }}
      notCoded={drinkingSampleNotCoded}
    >
      <UtteranceLink n={25} />
      <UtteranceLink n={31} />
    </CodedTranscriptProvider>,
  );
}

const row = (n: number) => document.getElementById(`utt-${n}`) as HTMLElement;
let scroll: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scroll = vi.fn();
  Element.prototype.scrollIntoView =
    scroll as unknown as typeof Element.prototype.scrollIntoView;
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.documentElement.classList.remove("dlg-open");
});

const reduced = (on: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: on && q.includes("reduce"),
    media: q,
    addEventListener() {},
    removeEventListener() {},
  }));

describe("UtteranceLink", () => {
  it("is a button labelled with the number and an accessible name", () => {
    view();
    const b = screen.getByRole("button", { name: "Open utterance 25" });
    expect(b.textContent).toBe("25");
    expect(b.getAttribute("type")).toBe("button");
  });

  it("opens the dialog and scrolls row 25 to the centre (smooth by default)", () => {
    reduced(false);
    view();
    fireEvent.click(screen.getByRole("button", { name: "Open utterance 25" }));
    expect(document.querySelector("dialog")!.hasAttribute("open")).toBe(true);
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(scroll.mock.instances[0]).toBe(row(25));
    expect(scroll).toHaveBeenCalledWith({
      block: "center",
      behavior: "smooth",
    });
  });

  it("highlights the row for about 1.5 s then removes the class", () => {
    vi.useFakeTimers();
    view();
    fireEvent.click(screen.getByRole("button", { name: "Open utterance 25" }));
    expect(row(25).classList.contains("hl")).toBe(true);
    vi.advanceTimersByTime(1400);
    expect(row(25).classList.contains("hl")).toBe(true);
    vi.advanceTimersByTime(200);
    expect(row(25).classList.contains("hl")).toBe(false);
  });

  it("moves the highlight when another link is used", () => {
    vi.useFakeTimers();
    view();
    fireEvent.click(screen.getByRole("button", { name: "Open utterance 25" }));
    fireEvent.click(screen.getByRole("button", { name: "Open utterance 31" }));
    expect(row(25).classList.contains("hl")).toBe(false);
    expect(row(31).classList.contains("hl")).toBe(true);
    expect(scroll).toHaveBeenCalledTimes(2);
  });

  it("with reduced motion scrolls instantly and still marks the row (static outline via CSS)", () => {
    reduced(true);
    view();
    fireEvent.click(screen.getByRole("button", { name: "Open utterance 25" }));
    expect(scroll).toHaveBeenCalledWith({ block: "center", behavior: "auto" });
    expect(row(25).classList.contains("hl")).toBe(true);
  });
});
