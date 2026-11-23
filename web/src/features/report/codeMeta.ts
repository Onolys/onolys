/** Per-code display metadata, in one place. The report carries ids only, no labels. */

const G_INFO = "Information & persuasion";
const G_QR = "Questions & reflections";
const G_ADH = "MI-adherent";
const G_NON = "MI non-adherent";

/** Pack ids (engines/miti pack.yaml) -> full label and group. */
export const CODE_META: Record<string, { label: string; group: string }> = {
  gi: { label: "Giving Information", group: G_INFO },
  persuade: { label: "Persuade", group: G_INFO },
  persuade_permission: { label: "Persuade with Permission", group: G_INFO },
  question: { label: "Question", group: G_QR },
  sr: { label: "Simple Reflection", group: G_QR },
  cr: { label: "Complex Reflection", group: G_QR },
  affirm: { label: "Affirm", group: G_ADH },
  seek_collab: { label: "Seek Collaboration", group: G_ADH },
  emphasize_autonomy: { label: "Emphasize Autonomy", group: G_ADH },
  confront: { label: "Confront", group: G_NON },
};

export const SHORT: Record<string, string> = {
  gi: "GI", persuade: "Persuade", persuade_permission: "PwP", question: "Q", sr: "SR", cr: "CR",
  affirm: "AF", seek_collab: "Seek", emphasize_autonomy: "EA", confront: "Confront",
};

export const GROUP_CLASS: Record<string, string> = {
  [G_INFO]: "c-info",
  [G_QR]: "c-qr",
  [G_ADH]: "c-mia",
  [G_NON]: "c-mina",
};
