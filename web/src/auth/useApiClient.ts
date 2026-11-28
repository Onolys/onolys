import { useMemo } from "react";
import { useAuth } from "@onolys/common/auth";
import { apiBaseUrl, createApiClient } from "../api/client";

/** API client wired to the auth service: per-request token, one forced refresh on 401, then sign-out. */
export function useApiClient() {
  const { service, signOut } = useAuth();
  return useMemo(
    () =>
      createApiClient({
        baseUrl: apiBaseUrl(),
        getToken: (force) => service.getToken(force),
        onSessionExpired: () => void signOut(),
      }),
    [service, signOut],
  );
}
