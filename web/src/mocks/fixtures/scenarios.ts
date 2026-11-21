/** Public scenario fields only (PRD R10): the prompt, hidden info and rules never leave the server. */
import type { components } from "../../api/schema";

export const MOCK_SCENARIOS: components["schemas"]["ScenarioPublic"][] = [
  { id: "sc_anxious_parent", title: "Anxious parent", difficulty: "easy", summary: "A parent worried about a child's persistent cough.", language: "en" },
  { id: "sc_reluctant_patient", title: "Reluctant patient", difficulty: "medium", summary: "A patient who minimises symptoms and resists follow-up.", language: "en" },
  { id: "sc_angry_relative", title: "Angry relative", difficulty: "hard", summary: "A relative upset about a delayed discharge.", language: "en" },
];

/** The staging voice list (config/staging/voice_providers.yaml). The API does not expose it yet; Task 11 gap. */
export const MOCK_VOICES = ["Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe"];
export const MOCK_DEFAULT_VOICE = "Kore";
export const MOCK_LIMITS = { max_s: 600, warn_s: 480 };
