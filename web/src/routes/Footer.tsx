import { Link } from "react-router";
import { CONTACT_EMAIL } from "../config";

export function Footer() {
  return (
    <footer className="app-footer">
      <ul data-inline-list>
        <li>Not official MITI coding and cannot be submitted as one.</li>
        <li>Use it to practice and prepare.</li>
        <li>Role-play or de-identified transcripts only.</li>
      </ul>
      <div className="footer-links">
        <Link to="/privacy">Privacy Policy</Link>
        <Link to="/terms">Terms of Service</Link>
        <a href={`mailto:${CONTACT_EMAIL}`}>Contact</a>
      </div>
      <p>
        Questions? Reach out to <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
      </p>
      <p className="copy">© {new Date().getFullYear()} Onolys. All rights reserved.</p>
    </footer>
  );
}
