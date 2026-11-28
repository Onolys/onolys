/**
 * Web build id, sent as `X-Client-Version` on every API request. `VITE_BUILD_SHA` is set by
 * the build (vite.config.ts fills it from `GITHUB_SHA` in CI); `dev` locally.
 */
export const WEB_VERSION: string = import.meta.env.VITE_BUILD_SHA || "dev";
