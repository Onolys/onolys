/**
 * Terminal view of a cancelled session (04-cancel R9): heading, whether it counted toward the limit
 * (`counted` null/undefined omits the sentence). No rating, speaker gate or retry.
 */
export function CancelledView({
  counted,
}: {
  counted: boolean | null | undefined;
}) {
  return (
    <>
      <h2 className="text-xl font-semibold">Cancelled</h2>
      {counted == null ? null : (
        <p role="status">
          Session cancelled. {counted ? "This counted toward your limit." : "This did not count toward your limit."}
        </p>
      )}
    </>
  );
}
