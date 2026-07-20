import { deriveConnectionPresentation } from "../../src/lib/connectionStatus.js";

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

const hostWaiting = {
  backendAvailable: true,
  currentView: "room-ready",
  peerCount: 1,
  channelStatus: "disconnected",
  isEncrypted: false,
  identityStatus: "unavailable"
};

test("a host alone cannot enter chat or claim a peer", () => {
  const state = deriveConnectionPresentation(hostWaiting);
  assert.equal(state.statusText, "Waiting for peer");
  assert.equal(state.occupancyText, "1/2 connected - waiting for peer");
  assert.equal(state.confirmedPeer, false);
  assert.equal(state.canHostEnterChat, false);
});

test("peer count alone cannot produce a connected claim", () => {
  const state = deriveConnectionPresentation({
    ...hostWaiting,
    peerCount: 2,
    channelStatus: "pending"
  });
  assert.equal(state.statusText, "Securing channel...");
  assert.equal(state.canHostEnterChat, false);
  assert.doesNotMatch(state.occupancyText, /2\/2 connected/i);
});

test("an inconsistent unencrypted confirmed state fails closed", () => {
  const state = deriveConnectionPresentation({
    ...hostWaiting,
    peerCount: 2,
    channelStatus: "confirmed",
    isEncrypted: false
  });
  assert.equal(state.confirmedPeer, false);
  assert.equal(state.canHostEnterChat, false);
  assert.doesNotMatch(state.occupancyText, /2\/2 connected/i);
});

test("mutually confirmed encryption permits host chat entry", () => {
  const state = deriveConnectionPresentation({
    ...hostWaiting,
    peerCount: 2,
    channelStatus: "confirmed",
    isEncrypted: true,
    identityStatus: "unverified"
  });
  assert.equal(state.statusText, "Identity verification required");
  assert.equal(state.occupancyText, "2/2 connected - verify before chatting");
  assert.equal(state.confirmedPeer, true);
  assert.equal(state.canHostEnterChat, true);
});

test("backend failure clears every connection claim", () => {
  const state = deriveConnectionPresentation({
    ...hostWaiting,
    backendAvailable: false,
    peerCount: 2,
    channelStatus: "confirmed",
    isEncrypted: true,
    identityStatus: "verified"
  });
  assert.equal(state.statusText, "Backend unavailable");
  assert.equal(state.confirmedPeer, false);
  assert.equal(state.canHostEnterChat, false);
});
