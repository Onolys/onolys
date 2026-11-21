import { FakeRelaySocket, type RelaySocket } from "./fakeRelay";

/**
 * Open the relay socket for `url` (`wss://<voice-host>/v1/voice/{id}`). Mock builds (`VITE_USE_MOCKS=true`:
 * dev:mock, PR previews, Storybook-style demos) get the in-page fake; everything else a real `WebSocket`.
 */
export function createRelaySocket(url: string, opts: { fake?: boolean } = {}): RelaySocket {
  const fake = opts.fake ?? import.meta.env.VITE_USE_MOCKS === "true";
  const s: RelaySocket = fake ? new FakeRelaySocket(url) : new WebSocket(url);
  s.binaryType = "arraybuffer";
  return s;
}
