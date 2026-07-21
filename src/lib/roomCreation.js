/**
 * Accept room metadata only when the backend confirms the atomic create transaction.
 *
 * @param {unknown} response
 * @param {string} fallbackName
 */
export function parseRoomCreationResponse(response, fallbackName) {
  const parsed = JSON.parse(String(response));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Backend returned an invalid room response");
  }

  const payload = /** @type {Record<string, unknown>} */ (parsed);
  if (payload.error) throw new Error(String(payload.error));
  if (payload.status !== "ready") throw new Error("Backend did not confirm room readiness");

  const onionAddress = String(payload.onion_address || "").trim();
  const shareLink = String(payload.share_link || "").trim();
  if (!onionAddress || !shareLink) {
    throw new Error("Backend did not return a complete room invitation");
  }

  return {
    friendlyName: String(payload.friendly_name || fallbackName),
    onionAddress,
    shareLink
  };
}
