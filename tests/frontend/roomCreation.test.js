import { parseRoomCreationResponse } from "../../src/lib/roomCreation.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  },
  /** @param {() => unknown} run @param {RegExp} pattern */
  throws(run, pattern) {
    try {
      run();
    } catch (error) {
      if (pattern.test(String(error))) return;
      throw new Error(`Unexpected error: ${String(error)}`);
    }
    throw new Error("Expected function to throw");
  }
};

const invitation = "mutinychat://join?v=3&onion=example.onion&host_key=public-key";
const ready = parseRoomCreationResponse(
  JSON.stringify({
    status: "ready",
    friendly_name: "test-room",
    onion_address: "example.onion",
    share_link: invitation
  }),
  "fallback-room"
);

assert.equal(ready.friendlyName, "test-room");
assert.equal(ready.onionAddress, "example.onion");
assert.equal(ready.shareLink, invitation);

assert.throws(
  () => parseRoomCreationResponse('{"error":"listener failed"}', "fallback-room"),
  /listener failed/
);
assert.throws(
  () =>
    parseRoomCreationResponse(
      '{"status":"ready","friendly_name":"test-room","onion_address":"example.onion"}',
      "fallback-room"
    ),
  /complete room invitation/
);
assert.throws(
  () =>
    parseRoomCreationResponse(
      '{"status":"creating","onion_address":"example.onion","share_link":"pending"}',
      "fallback-room"
    ),
  /did not confirm room readiness/
);

console.log("roomCreation frontend tests passed");
