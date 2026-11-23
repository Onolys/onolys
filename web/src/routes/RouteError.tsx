import { Link } from "react-router";

/** Root error element: a render crash keeps the layout and a way back. */
export function RouteError() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="mt-4">
        <Link to="/" className="text-primary underline underline-offset-4">
          Back to the start
        </Link>
      </p>
    </>
  );
}
