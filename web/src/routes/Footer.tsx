import { Link } from "react-router";
import { Footer as UiFooter } from "@onolys/ui";
import { CONTACT_EMAIL } from "../config";
import { ThemeToggle } from "./ThemeToggle";

const NOTICES = ["Not official MITI coding", "Use it to practice and prepare", "Role-play or de-identified transcripts only"];

/** Compact two-row footer: three notices, then Privacy / Terms / Contact / Sample report, then copyright. */
export function Footer() {
  return (
    <UiFooter
      className="relative [&_a]:min-w-0! [&_a]:underline flex flex-wrap items-center justify-center gap-x-4 gap-y-0 space-y-0 px-gutter py-3 text-center text-xs [&>div]:text-xs [&>nav]:w-full [&>nav]:justify-center [&>nav]:gap-x-5 [&>div:last-child]:w-full"
      notices={
        <ul className="m-0 flex w-full list-none flex-wrap justify-center gap-x-2 p-0">
          {NOTICES.map((n) => (
            <li key={n} className="not-first:before:mr-2 not-first:before:content-['·']">
              {n}
            </li>
          ))}
        </ul>
      }
      links={
        <>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <a href={`mailto:${CONTACT_EMAIL}`}>Contact</a>
          <Link to="/sample" target="_blank" rel="noopener noreferrer">
            Sample report
          </Link>
        </>
      }
      copyright={
        <>
          © {new Date().getFullYear()} Onolys
          <ThemeToggle className="absolute right-3 bottom-2" />
        </>
      }
    />
  );
}
