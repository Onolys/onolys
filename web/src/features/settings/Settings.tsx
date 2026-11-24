/** `/settings`: usage and account-removal contact. */
import { Button } from "@onolys/ui";
import { describeError } from "../../api/errors";
import { H1, LINK, NOTE } from "../../components/classes";
import { CONTACT_EMAIL } from "../../config";
import { formatResetTime } from "../../lib/format";
import { UsageLeft } from "../usage/UsageLeft";
import { useUsage } from "../usage/useUsage";
import { ErrorCard } from "../session/ErrorCard";

const H2 = "m-0 text-xl font-semibold";
const SECTION = "grid gap-3";

export function Settings() {
  const usage = useUsage();
  const usageErr = usage.error ? describeError(usage.error) : null;
  const removal = <a className={LINK} href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

  return (
    <div className="grid gap-6">
      <h1 className={H1}>Settings</h1>

      <section aria-labelledby="usage-h" className={SECTION}>
        <h2 id="usage-h" className={H2}>
          Usage
        </h2>
        {usage.data ? (
          <>
            <p>
              Ratings: <UsageLeft kind="eval" period="day" />
              {formatResetTime(usage.data.eval.day.resets_at)
                ? `. Daily limit resets at ${formatResetTime(usage.data.eval.day.resets_at)}`
                : ""}
            </p>
            <p>
              Interviews: <UsageLeft kind="interview" period="day" />
            </p>
          </>
        ) : usage.isError ? (
          <ErrorCard code={usageErr?.code} reference={usageErr?.requestId} message="We couldn't load your usage.">
            <Button type="button" variant="secondary" onClick={() => void usage.refetch()}>
              Retry
            </Button>
          </ErrorCard>
        ) : (
          <p className={NOTE}>Loading…</p>
        )}
      </section>

      <section aria-labelledby="account-h" className={SECTION}>
        <h2 id="account-h" className={H2}>
          Account
        </h2>
        <p>
          Deleting a session removes its audio, transcript, rating and reports. For account removal, contact {removal}.
        </p>
      </section>
    </div>
  );
}
