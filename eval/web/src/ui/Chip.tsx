import { CircleCheck, CircleX, Info, Minus, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import "./ui.css";

export type ChipTone = "success" | "warning" | "danger" | "neutral" | "muted" | "info";

const ICONS: Record<ChipTone, ReactNode> = {
  success: <CircleCheck aria-hidden="true" />,
  warning: <TriangleAlert aria-hidden="true" />,
  danger: <CircleX aria-hidden="true" />,
  info: <Info aria-hidden="true" />,
  neutral: <Minus aria-hidden="true" />,
  muted: <Minus aria-hidden="true" />,
};

/** Status chip: always icon + text, so meaning never depends on colour alone. Pass `icon` to override the tone's default icon. */
export function Chip({ tone = "neutral", icon, mono, children }: { tone?: ChipTone; icon?: ReactNode; mono?: boolean; children: ReactNode }) {
  return <span className={`ui-chip ui-chip-${tone}${mono ? " ui-chip-mono" : ""}`}>{icon ?? ICONS[tone]}{children}</span>;
}
