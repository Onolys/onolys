import { Link } from "react-router";
import { Footer as UiFooter, ThemeToggle } from "@onolys/common";
import { CONTACT_EMAIL } from "../config";

const NOTICES = ["Not official MITI coding", "Use it to practice and prepare", "Role-play or de-identified transcripts only"];

/** Compact two-row footer: notices, then legal links and copyright. */
export function Footer() {
  return (
    <UiFooter
      compact
      themeToggle={<ThemeToggle />}
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
          <span className="whitespace-nowrap text-footer-muted">© {new Date().getFullYear()} Onolys</span>
        </>
      }
    />
  );
}
