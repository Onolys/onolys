import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { messageForCode } from "../../api/errors";
import { UploadFailedView } from "./UploadFailedView";

const show = (code: string | null) =>
  render(
    <MemoryRouter>
      <UploadFailedView code={code} reference="s_abc123" />
    </MemoryRouter>,
  );

describe("UploadFailedView (PRD R11)", () => {
  it.each(["audio_unreadable", "audio_too_large", "unsupported_audio", "audio_too_long", "interview_too_long"])(
    "%s: shows the existing per-code reason, the way back and the Reference",
    (code) => {
      show(code);
      const reason = messageForCode(code).replace(/\.$/, "");
      expect(screen.getByRole("alert")).toHaveTextContent(`Upload failed: ${reason}. Choose a different file.`);
      expect(screen.getByRole("link", { name: /choose a different file/i })).toHaveAttribute("href", "/sessions/new");
      expect(screen.getByText("Reference: s_abc123")).toBeInTheDocument();
    },
  );

  it("an unknown code still reads as an upload failure with generic copy", () => {
    show(null);
    expect(screen.getByRole("alert")).toHaveTextContent(/^Upload failed: Something went wrong\. Please try again\. Choose a different file\./);
  });
});
