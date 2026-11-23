/**
 * TEMPORARY (Task 2): routes.tsx still mounts this at `/` until Task 3 wires `/new` and `/sessions`.
 * Composes the two split pages' bodies under the old "Sessions" heading; remove in Task 3.
 */
import { NewSessionCards } from "./NewSessionChooser";
import { SessionsList } from "./SessionsPage";

export function Dashboard() {
  return (
    <>
      <h1>Sessions</h1>
      <NewSessionCards />
      <SessionsList />
    </>
  );
}
