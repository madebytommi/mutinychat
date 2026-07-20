const BACKEND_TOR_STATUSES = new Set(["stopped", "ready", "failed"]);

/**
 * @typedef {{
 *   status: "stopped" | "starting" | "ready" | "failed",
 *   routeActive: boolean,
 *   error: string
 * }} TorState
 */

/** @param {Record<string, unknown> | null | undefined} payload @returns {TorState} */
export function mapBackendTorState(payload) {
  const rawStatus = typeof payload?.tor_status === "string" ? payload.tor_status : "stopped";
  const status = BACKEND_TOR_STATUSES.has(rawStatus) ? rawStatus : "failed";
  return {
    status: /** @type {"stopped" | "ready" | "failed"} */ (status),
    routeActive: status === "ready" && payload?.tor_route_active === true,
    error: status === "failed" && typeof payload?.tor_error === "string" ? payload.tor_error : ""
  };
}

/** @param {TorState} state */
export function torBadgeText(state) {
  if (state.routeActive) return "Room via Tor";
  if (state.status === "starting") return "Tor starting...";
  if (state.status === "ready") return "Tor ready";
  if (state.status === "failed") return "Tor unavailable";
  return "Tor off";
}

/** @param {TorState} state */
export function torBadgeDescription(state) {
  if (state.routeActive) {
    return "This room's peer connection uses Tor. This does not claim that all application traffic is proxied.";
  }
  if (state.status === "starting") return "Tor is starting; no room route is confirmed yet.";
  if (state.status === "ready") return "Tor is running, but no current room route is active.";
  if (state.status === "failed") return state.error || "Tor is not available.";
  return "Tor is not running.";
}
