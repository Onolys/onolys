/** `/new` (PRD SP1): the two landing cards, AI interview and rate a recording, with usage and cap behaviour. */
import { Link } from "react-router";
import { messageForCode } from "../../api/errors";
import { interviewCapText } from "../interview/capText";
import { UsageLeft } from "../usage/UsageLeft";
import { blockingPeriod, formatBlockingReset } from "../usage/usage";
import { useUsage } from "../usage/useUsage";

export function NewSessionChooser() {
  const usage = useUsage();
  const blocking = blockingPeriod(usage.data, "eval");
  const interviewBlocking = blockingPeriod(usage.data, "interview");
  return (
    <>
      <h1>New Session</h1>
      <div className="landing-cards">
        <section className="landing-card" aria-labelledby="card-interview">
          <h2 id="card-interview">Practise with an AI client</h2>
          <p className="form-note">
            A 10-minute role-play, then rated like any recording.
            {usage.data ? (
              <>
                {" "}
                <UsageLeft kind="interview" period="day" />
              </>
            ) : null}
          </p>
          {interviewBlocking ? (
            <>
              <button type="button" className="btn btn-primary" disabled>
                Start AI Interview
              </button>
              <p className="notice">{interviewCapText(interviewBlocking)}</p>
            </>
          ) : (
            <Link className="btn btn-primary" to="/interviews/new">
              Start AI Interview
            </Link>
          )}
        </section>
        <section className="landing-card" aria-labelledby="card-upload">
          <h2 id="card-upload">Rate a recording</h2>
          <p className="form-note">
            Bring a session you recorded.
            {usage.data ? (
              <>
                {" "}
                <UsageLeft kind="eval" period="day" />
              </>
            ) : null}
          </p>
          <Link className="btn btn-primary" to="/sessions/new">
            New session
          </Link>
          {blocking ? (
            <p className="notice">
              {messageForCode("daily_cap_reached", {
                resetsAt: formatBlockingReset(blocking),
              })}
            </p>
          ) : null}
        </section>
      </div>
    </>
  );
}
