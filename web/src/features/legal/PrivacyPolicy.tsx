import { CONTACT_EMAIL } from "../../config";
import { LegalPage } from "./LegalPage";

export function PrivacyPolicy() {
  const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;
  return (
    <LegalPage title="Privacy Policy">
      <p>This policy explains what Onolys collects when you practice MITI coding, why, and the control you keep.</p>

      <h2>Your data is yours</h2>
      <ul>
        <li>Your data is stored only for you, under your account.</li>
        <li>
          No other user can access your sessions, transcripts and reports. Our service and the providers listed below process
          them only to run Onolys.
        </li>
        <li>You have full control over your data.</li>
        <li>You can delete your data at any time.</li>
      </ul>

      <h2>What we collect</h2>
      <ul>
        <li>Your account email address and sign-in details (managed by Firebase Authentication).</li>
        <li>Session audio you upload, and the transcripts made from it.</li>
        <li>
          Practice-interview audio: if you run an AI practice interview, your voice is streamed to Google Gemini Live (on Google
          Cloud Vertex AI) and the recording becomes a session. We also keep interview records: the scenario, the voice, the
          duration and the interview state.
        </li>
        <li>Your API key, if you create one: we store only a hash of it and when it was created and last used, never the key itself.</li>
        <li>Ratings you submit, and the coding reports we generate for your sessions.</li>
        <li>Basic usage counters (for example, how many sessions you ran in a day) to apply fair-use limits.</li>
      </ul>

      <h2>Why we collect it</h2>
      <p>Only to provide the service: transcribe your session, code it, and show you the report. We do not sell your data.</p>

      <h2>Please upload only role-play or de-identified sessions</h2>
      <p>Onolys is a practice tool. Do not upload recordings or transcripts that identify real patients.</p>

      <h2>How to delete your data</h2>
      <p>
        Open a session and choose Delete. This permanently removes that session&apos;s audio, transcript, rating and all report
        versions. Usage counters and interview records (scenario, voice and duration of any practice interview) are kept. To
        remove your whole account and everything in it, including those, contact us at {mail} and we will do it for you.
      </p>

      <h2>Service providers</h2>
      <p>We use these providers to run Onolys, only for that purpose:</p>
      <ul>
        <li>Google Cloud and Firebase: sign-in, database and file storage, and speech-to-text.</li>
        <li>Google Gemini and Anthropic Claude: AI models that read your transcript to produce coding and tips.</li>
      </ul>

      <h2>Security</h2>
      <p>
        Data is kept in access-controlled cloud storage and sent over encrypted connections. No system is perfectly secure, so
        tell us right away if you suspect a problem.
      </p>

      <h2>Contact</h2>
      <p>Questions or requests: {mail}.</p>
    </LegalPage>
  );
}
