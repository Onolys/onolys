import { describe, expect, it } from "vitest";
import { AUDIO_ENGINE, clientInfo } from "./clientInfo";

describe("clientInfo", () => {
  it("reports the recorder mime and the audio engine name plus version", () => {
    expect(AUDIO_ENGINE).toMatch(/^[a-z0-9-]+@\d+$/);
    expect(clientInfo({ mimeType: "audio/webm;codecs=opus" })).toEqual({
      recorder_mime: "audio/webm;codecs=opus",
      audio_engine: AUDIO_ENGINE,
    });
  });

  it("omits an empty recorder mime (browser default)", () => {
    expect(clientInfo({ mimeType: "" })).toEqual({ audio_engine: AUDIO_ENGINE });
  });
});
