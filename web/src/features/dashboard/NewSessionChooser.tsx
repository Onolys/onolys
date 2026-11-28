/** `/new`: the two landing cards, AI interview and rate a recording, with usage and cap behaviour. */
import { Button, Card, CardContent, CardDescription, CardFooter, CardHeader, Section, H1, PAGE, Notice } from "@onolys/common";
import { Link } from "react-router";
import { useAuth } from "@onolys/common/auth";
import { messageForCode } from "../../api/errors";
import { interviewCapText } from "../interview/capText";
import { UsageCount } from "../usage/UsageCount";
import { blockingPeriod, formatBlockingReset } from "../usage/usage";
import { useUsage } from "../usage/useUsage";

const TITLE = "m-0 text-lg font-semibold leading-tight";

/** Firebase displayName (trimmed), else the email's local part, else nothing. */
export function greetingName(user: { displayName?: string | null; email?: string | null } | null): string {
  const name = user?.displayName?.trim();
  if (name) return name;
  return user?.email?.split("@")[0]?.trim() ?? "";
}

export function NewSessionChooser() {
  const { user } = useAuth();
  const name = greetingName(user);
  const usage = useUsage();
  const blocking = blockingPeriod(usage.data, "eval");
  const interviewBlocking = blockingPeriod(usage.data, "interview");
  return (
    <div className={PAGE}>
      <h1 className={H1}>{name ? `Welcome ${name}` : "Welcome"}</h1>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(16rem,1fr))] gap-4">
        <Section aria-labelledby="card-interview" className="flex">
          <Card className="w-full">
            <CardHeader>
              <h2 id="card-interview" className={TITLE}>
                Practise with an AI client
              </h2>
              <CardDescription>A 10-minute role-play, then rated like any recording.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {interviewBlocking ? <Notice>{interviewCapText(interviewBlocking)}</Notice> : null}
            </CardContent>
            <CardFooter className="justify-between">
              {interviewBlocking ? (
                <Button type="button" disabled>
                  Start AI Interview
                </Button>
              ) : (
                <Button asChild>
                  <Link to="/interviews/new">Start AI Interview</Link>
                </Button>
              )}
              <UsageCount kind="interview" />
            </CardFooter>
          </Card>
        </Section>
        <Section aria-labelledby="card-upload" className="flex">
          <Card className="w-full">
            <CardHeader>
              <h2 id="card-upload" className={TITLE}>
                Rate a recording
              </h2>
              <CardDescription>Bring a session you recorded.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {blocking ? (
                <Notice>
                  {messageForCode("daily_cap_reached", {
                    resetsAt: formatBlockingReset(blocking),
                  })}
                </Notice>
              ) : null}
            </CardContent>
            <CardFooter className="justify-between">
              <Button asChild>
                <Link to="/sessions/new">New session</Link>
              </Button>
              <UsageCount kind="eval" />
            </CardFooter>
          </Card>
        </Section>
      </div>
    </div>
  );
}
