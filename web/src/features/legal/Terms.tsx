import { CONTACT_EMAIL } from "../../config";
import { LegalPage } from "./LegalPage";

export function Terms() {
  return (
    <LegalPage title="Terms of Service">
      <p>By using Onolys you agree to these terms.</p>

      <h2>A practice tool</h2>
      <p>
        Onolys helps you practice and prepare for MITI coding. It is not official MITI coding and cannot be submitted as one. It
        gives no clinical or medical advice.
      </p>

      <h2>Role-play or de-identified content only</h2>
      <p>Upload only role-play or de-identified recordings and transcripts. Do not upload real patient health information.</p>

      <h2>Your account</h2>
      <p>You are responsible for your account and for keeping your sign-in details and any API key private.</p>

      <h2>Acceptable use</h2>
      <p>Do not misuse the service, try to break or overload it, access other people&apos;s data, or use it unlawfully.</p>

      <h2>Your content</h2>
      <p>Your content remains yours. You allow us to process it only to provide the service to you.</p>

      <h2>No warranty, limited liability</h2>
      <p>
        The service is provided &quot;as is&quot;, without warranties of any kind. To the extent the law allows, Onolys is not
        liable for any indirect or consequential loss arising from its use.
      </p>

      <h2>Changes</h2>
      <p>We may update these terms. The date at the top shows the latest version; continued use means you accept it.</p>

      <h2>Contact</h2>
      <p>
        Questions: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>
    </LegalPage>
  );
}
