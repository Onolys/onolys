/** Display name for an internal eval session id (the dataset session name); falls back to the id when the server sent no label. Ids stay the keys, URL params and API arguments. */
export type SessionLabels = Record<string, string> | undefined;
export const sessionLabel = (labels: SessionLabels, sessionId: string): string => labels?.[sessionId] || sessionId;
