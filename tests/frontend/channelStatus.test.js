import {
  channelBadgeText,
  mapBackendSecurityState,
  peerVerifiedMarkerEffect
} from "../../src/lib/channelStatus.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  },
  /** @param {string} value @param {RegExp} pattern */
  doesNotMatch(value, pattern) {
    if (pattern.test(value)) throw new Error(`Expected ${value} not to match ${String(pattern)}`);
  }
};

/** @param {string} name @param {() => void} run */
function test(name, run) {
  run();
  console.log(`ok - ${name}`);
}

test("pending state never claims E2EE or identity verification", () => {
  const state = mapBackendSecurityState({
    channel_status: "pending",
    encrypted: true,
    identity_status: "verified",
    verified: true,
    verification_code: "should-clear"
  });
  assert.equal(state.channelStatus, "pending");
  assert.equal(state.isEncrypted, false);
  assert.equal(state.isPeerVerified, false);
  assert.equal(state.verificationCode, "");
  assert.equal(channelBadgeText(state.channelStatus), "Securing channel…");
  assert.doesNotMatch(channelBadgeText(state.channelStatus), /E2EE|🔒/);
});

test("failed state clears stale confirmed and identity state", () => {
  const state = mapBackendSecurityState({
    channel_status: "failed",
    channel_error: "confirmation failed",
    encrypted: true,
    identity_status: "verified",
    verified: true,
    verification_local_confirmed: true,
    verification_peer_confirmed: true
  });
  assert.equal(state.channelStatus, "failed");
  assert.equal(state.channelError, "confirmation failed");
  assert.equal(state.isEncrypted, false);
  assert.equal(state.isPeerVerified, false);
  assert.equal(state.verificationLocalConfirmed, false);
  assert.equal(state.verificationPeerConfirmed, false);
  assert.equal(channelBadgeText(state.channelStatus), "Secure channel failed");
});

test("confirmed channel remains separate from unverified identity", () => {
  const state = mapBackendSecurityState({
    channel_status: "confirmed",
    encrypted: true,
    identity_status: "unverified",
    verified: false,
    verification_code: "12345 67890 12345 67890"
  });
  assert.equal(state.isEncrypted, true);
  assert.equal(state.identityStatus, "unverified");
  assert.equal(state.isPeerVerified, false);
  assert.equal(channelBadgeText(state.channelStatus), "🔒 E2EE channel confirmed");
});

test("identity is verified only inside a confirmed channel", () => {
  const state = mapBackendSecurityState({
    channel_status: "confirmed",
    encrypted: true,
    identity_status: "verified",
    verified: true
  });
  assert.equal(state.isEncrypted, true);
  assert.equal(state.identityStatus, "verified");
  assert.equal(state.isPeerVerified, true);
});

test("missing backend state after restart fails closed", () => {
  const state = mapBackendSecurityState({});
  assert.equal(state.channelStatus, "disconnected");
  assert.equal(state.isEncrypted, false);
  assert.equal(state.isPeerVerified, false);
  assert.equal(state.verificationCode, "");
});

test("inconsistent confirmed response is treated as failed", () => {
  const state = mapBackendSecurityState({
    channel_status: "confirmed",
    encrypted: false,
    identity_status: "verified",
    verified: true
  });
  assert.equal(state.channelStatus, "failed");
  assert.equal(state.isEncrypted, false);
  assert.equal(state.isPeerVerified, false);
});

test("peer verified marker requests a poll without granting identity", () => {
  const state = mapBackendSecurityState({
    channel_status: "failed",
    encrypted: false,
    identity_status: "unavailable",
    verified: false
  });
  const effect = peerVerifiedMarkerEffect(state);

  assert.equal(effect.requestPoll, true);
  assert.equal(effect.showNotification, false);
  assert.equal(state.isPeerVerified, false);
  assert.equal(state.identityStatus, "unavailable");
});

test("authoritative poll after marker updates verified identity", () => {
  const before = mapBackendSecurityState({
    channel_status: "confirmed",
    encrypted: true,
    identity_status: "pending",
    verified: false
  });
  const effect = peerVerifiedMarkerEffect(before);
  const after = mapBackendSecurityState({
    channel_status: "confirmed",
    encrypted: true,
    identity_status: "verified",
    verified: true
  });

  assert.equal(effect.requestPoll, true);
  assert.equal(before.isPeerVerified, false);
  assert.equal(after.isPeerVerified, true);
  assert.equal(after.identityStatus, "verified");
});
