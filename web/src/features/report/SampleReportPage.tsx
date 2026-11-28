/**
 * `/sample`: the bundled made-up report and transcript, rendered through the
 * same view as the real page. Public, read-only, and makes no network request.
 */
import {
  drinkingSampleNotCoded,
  drinkingSampleReport,
  drinkingSampleTurns,
} from "../../mocks/fixtures/sample";
import { NOTE } from "../../components/classes";
import { ReportView, type TurnsState } from "./ReportView";

const TURNS: TurnsState = { status: "ready", turns: drinkingSampleTurns };

export function SampleReportPage() {
  return (
    <ReportView
      report={drinkingSampleReport}
      turns={TURNS}
      title="Sample report"
      notCoded={drinkingSampleNotCoded}
      headerSlot={<p className={NOTE}>Example report from a made-up role-play conversation.</p>}
    />
  );
}
