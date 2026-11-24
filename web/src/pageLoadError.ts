import { ApiError } from "./api/errors";

/** Opt in only for essential page reads. Background failures keep usable cached content. */
export function pageLoadError(error: Error, query: { state: { data: unknown } }): boolean {
  return query.state.data === undefined && (!(error instanceof ApiError) || error.status >= 500);
}
