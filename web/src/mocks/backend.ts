import { createMemoryStatusEmitter } from "../api/statusListener";
import { MockBackend } from "./stateMachine";

/** Shared singletons for MSW handlers, the browser worker and tests. */
export const mockEmitter = createMemoryStatusEmitter({ reportMissing: true });
export const mockBackend = new MockBackend({ emitter: mockEmitter });
