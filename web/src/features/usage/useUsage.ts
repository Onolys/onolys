/** The one `/usage` consumer. Invalidate `USAGE_KEY` after a run starts. */
import { useQuery } from "@tanstack/react-query";
import { unwrap } from "../../api/client";
import { useApiClient } from "../../auth/useApiClient";

export const USAGE_KEY = ["usage"] as const;

export function useUsage(opts: { enabled?: boolean } = {}) {
  const client = useApiClient();
  return useQuery({
    queryKey: USAGE_KEY,
    enabled: opts.enabled ?? true,
    queryFn: async () => unwrap(await client.GET("/usage")),
  });
}
