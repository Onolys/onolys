import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api/errors";

/** One retry for network/5xx failures; a 4xx will not change on retry. */
function retryTransient(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 1;
}

/** In-memory only, short-lived cache: no PHI persisted (PRD R8, D3). */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { gcTime: 2 * 60 * 1000, staleTime: 0, retry: retryTransient, refetchOnWindowFocus: false },
    },
  });
}
