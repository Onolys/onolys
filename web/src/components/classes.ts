/** Layout/text class constants shared by migrated screens (semantic tokens only; browser defaults return inside `.app`). */
export const H1 = "m-0 text-2xl font-semibold";
/** Page stack: heading, notices, forms. Paragraph margins are zeroed (preflight already does; kept explicit). */
export const PAGE = "grid gap-4 [&_p]:m-0";
export const NOTE = "text-sm text-muted-foreground";
export const LINK = "text-primary underline underline-offset-4";
/** Buttons need `border-0` inside `.app`; link-style buttons also drop the background. */
export const BTN = "border-0 no-underline";
export const LINK_BTN = "border-0 bg-transparent px-0";
export const ACTIONS = "flex flex-wrap items-center gap-3";
