/** Server-published upload limits for the client pre-checks (PRD R10). Fetched once, kept long. */
import { useQuery } from "@tanstack/react-query";
import { unwrap } from "../../api/client";
import { useApiClient } from "../../auth/useApiClient";
import type { UploadLimits } from "./precheck";

export const UPLOAD_LIMITS_KEY = ["upload-limits"] as const;
const STALE_MS = 60 * 60 * 1000;

export function useUploadLimits(): UploadLimits | undefined {
  const client = useApiClient();
  const q = useQuery({
    queryKey: UPLOAD_LIMITS_KEY,
    staleTime: STALE_MS,
    retry: false, // fail open: a missing answer just skips the client checks
    queryFn: async () => {
      return unwrap(await client.GET("/upload-limits"));
    },
  });
  return q.data;
}
