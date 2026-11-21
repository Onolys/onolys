import { Link } from "react-router";

/** Root error element: a render crash keeps the layout and a way back. */
export function RouteError() {
  return (
    <>
      <h1>Something went wrong</h1>
      <p>
        <Link to="/">Back to the start</Link>
      </p>
    </>
  );
}
