const CHANNEL_STATUSES = new Set(["disconnected", "pending", "confirmed", "failed"]);
const IDENTITY_STATUSES = new Set(["unavailable", "unverified", "pending", "verified"]);

/**
 * Convert the backend security response into fail-closed frontend state.
 * @param {Record<string, unknown> | null | undefined} payload
 */
export function mapBackendSecurityState(payload) {
  const value = payload && typeof payload === "object" ? payload : {};
  const reportedChannelStatus = CHANNEL_STATUSES.has(String(value.channel_status))
    ? String(value.channel_status)
    : "disconnected";
  const channelConfirmed = reportedChannelStatus === "confirmed" && value.encrypted === true;
  const channelStatus = reportedChannelStatus === "confirmed" && !channelConfirmed
    ? "failed"
    : reportedChannelStatus;
  const reportedIdentityStatus = IDENTITY_STATUSES.has(String(value.identity_status))
    ? String(value.identity_status)
    : "unavailable";
  const identityStatus = channelConfirmed ? reportedIdentityStatus : "unavailable";
  const identityVerified = channelConfirmed
    && identityStatus === "verified"
    && value.verified === true;

  return {
    channelStatus,
    channelError: channelStatus === "failed" ? String(value.channel_error || "") : "",
    isEncrypted: channelConfirmed,
    identityStatus: identityVerified ? "verified" : identityStatus,
    isPeerVerified: identityVerified,
    verificationCode: channelConfirmed ? String(value.verification_code || "") : "",
    verificationLocalConfirmed: channelConfirmed
      ? Boolean(value.verification_local_confirmed)
      : false,
    verificationPeerConfirmed: channelConfirmed
      ? Boolean(value.verification_peer_confirmed)
      : false
  };
}

/** @param {string} channelStatus */
export function channelBadgeText(channelStatus) {
  if (channelStatus === "pending") return "Securing channel…";
  if (channelStatus === "failed") return "Secure channel failed";
  if (channelStatus === "confirmed") return "🔒 E2EE channel confirmed";
  return "No E2EE channel";
}

/**
 * A peer-verified marker is only a hint to refresh authoritative backend state.
 * @param {{ channelStatus?: string, identityStatus?: string, isPeerVerified?: boolean }} state
 */
export function peerVerifiedMarkerEffect(state) {
  return {
    requestPoll: true,
    showNotification: state.channelStatus === "confirmed"
      && state.identityStatus === "verified"
      && state.isPeerVerified === true
  };
}
