export const FRONTEND_CONTROL_EVENTS = Object.freeze({
  CHANNEL_FAILED: "channel_failed",
  PEER_JOINED: "peer_joined",
  PEER_LEFT: "peer_left",
  PEER_VERIFIED: "peer_verified",
  ROOM_DELETED: "room_deleted"
});

const VALID_CONTROL_EVENTS = /** @type {Set<string>} */ (
  new Set(Object.values(FRONTEND_CONTROL_EVENTS))
);

/** @typedef {{ kind: "chat", text: string } | { kind: "control", event: string }} FrontendEvent */

/** @param {unknown} value @returns {FrontendEvent | null} */
export function parseFrontendEvent(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = /** @type {Record<string, unknown>} */ (value);

  if (candidate.kind === "chat" && typeof candidate.text === "string") {
    return { kind: "chat", text: candidate.text };
  }
  if (
    candidate.kind === "control" &&
    typeof candidate.event === "string" &&
    VALID_CONTROL_EVENTS.has(candidate.event)
  ) {
    return { kind: "control", event: candidate.event };
  }
  return null;
}
