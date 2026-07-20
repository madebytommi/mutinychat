import {
  mapBackendTorState,
  torBadgeDescription,
  torBadgeText
} from "../../src/lib/torStatus.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  },
  /** @param {string} value @param {RegExp} pattern */
  match(value, pattern) {
    if (!pattern.test(value)) throw new Error(`Expected ${value} to match ${String(pattern)}`);
  }
};

/** @param {string} name @param {() => void} run */
function test(name, run) {
  run();
  console.log(`ok - ${name}`);
}

test("a live Tor runtime without a room is only ready", () => {
  const state = mapBackendTorState({ tor_status: "ready", tor_route_active: false });
  assert.equal(state.status, "ready");
  assert.equal(state.routeActive, false);
  assert.equal(torBadgeText(state), "Tor ready");
});

test("the badge claims Tor routing only for an authoritative current room", () => {
  const state = mapBackendTorState({ tor_status: "ready", tor_route_active: true });
  assert.equal(state.routeActive, true);
  assert.equal(torBadgeText(state), "Room via Tor");
  assert.match(torBadgeDescription(state), /room's peer connection/i);
  assert.match(torBadgeDescription(state), /does not claim.*all application traffic/i);
});

test("a stale route flag cannot override a failed Tor runtime", () => {
  const state = mapBackendTorState({
    tor_status: "failed",
    tor_route_active: true,
    tor_error: "Tor process is no longer running"
  });
  assert.equal(state.routeActive, false);
  assert.equal(torBadgeText(state), "Tor unavailable");
  assert.equal(torBadgeDescription(state), "Tor process is no longer running");
});

test("missing and unknown backend state fail closed", () => {
  assert.equal(mapBackendTorState({}).routeActive, false);
  assert.equal(mapBackendTorState({ tor_status: "unexpected", tor_route_active: true }).status, "failed");
  assert.equal(mapBackendTorState({ tor_status: "unexpected", tor_route_active: true }).routeActive, false);
});
