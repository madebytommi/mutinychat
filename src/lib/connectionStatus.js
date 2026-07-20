/**
 * @typedef {{
 *   backendAvailable: boolean,
 *   currentView: string,
 *   peerCount: number,
 *   channelStatus: string,
 *   isEncrypted: boolean,
 *   identityStatus: string
 * }} ConnectionStateInput
 */

/** @param {ConnectionStateInput} input */
export function deriveConnectionPresentation(input) {
  const numericPeerCount = Number.isFinite(input.peerCount) ? Math.floor(input.peerCount) : 0;
  const peerCount = Math.max(0, Math.min(2, numericPeerCount));
  const confirmedPeer = Boolean(
    input.backendAvailable &&
      peerCount >= 2 &&
      input.channelStatus === "confirmed" &&
      input.isEncrypted
  );
  const verifiedPeer = confirmedPeer && input.identityStatus === "verified";

  if (!input.backendAvailable) {
    return {
      statusText: "Backend unavailable",
      occupancyText: "Connection state unavailable",
      confirmedPeer: false,
      verifiedPeer: false,
      canHostEnterChat: false
    };
  }

  if (input.channelStatus === "failed") {
    return {
      statusText: "Secure channel failed",
      occupancyText: "No confirmed peer connection",
      confirmedPeer: false,
      verifiedPeer: false,
      canHostEnterChat: false
    };
  }

  if (confirmedPeer) {
    return {
      statusText: verifiedPeer ? "Participant verified" : "Identity verification required",
      occupancyText: verifiedPeer
        ? "2/2 connected - participant verified"
        : "2/2 connected - verify before chatting",
      confirmedPeer: true,
      verifiedPeer,
      canHostEnterChat: true
    };
  }

  if (input.channelStatus === "pending" || peerCount >= 2) {
    return {
      statusText: "Securing channel...",
      occupancyText: "Peer present - secure channel not confirmed",
      confirmedPeer: false,
      verifiedPeer: false,
      canHostEnterChat: false
    };
  }

  if (input.currentView === "lobby") {
    return {
      statusText: "Disconnected",
      occupancyText: "No active room",
      confirmedPeer: false,
      verifiedPeer: false,
      canHostEnterChat: false
    };
  }

  return {
    statusText: "Waiting for peer",
    occupancyText: `${peerCount}/2 connected - waiting for peer`,
    confirmedPeer: false,
    verifiedPeer: false,
    canHostEnterChat: false
  };
}
