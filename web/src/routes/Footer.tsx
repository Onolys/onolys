import { Link } from "react-router";
import { CONTACT_EMAIL } from "../config";

export function Footer() {
  return (
    <footer className="app-footer">
      <ul className="footer-line" data-inline-list>
        <li>Not official MITI coding</li>
        <li>Use it to practice and prepare</li>
        <li>Role-play or de-identified transcripts only</li>
      </ul>
      <ul className="footer-line" data-inline-list>
        <li>
          <Link to="/privacy">Privacy</Link>
        </li>
        <li>
          <Link to="/terms">Terms</Link>
        </li>
        <li>
          <a href={`mailto:${CONTACT_EMAIL}`}>Contact</a>
        </li>
        <li>© {new Date().getFullYear()} Onolys</li>
      </ul>
    </footer>
  );
}
