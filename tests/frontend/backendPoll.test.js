import { isBackendPollBusy } from "../../src/lib/backendPoll.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  }
};

/** @param {string} name @param {() => void} run */
function test(name, run) {
  run();
  console.log(`ok - ${name}`);
}

test("busy poll responses preserve the last authoritative UI state", () => {
  assert.equal(isBackendPollBusy({ status: "busy" }), true);
});

test("ordinary and malformed poll responses are not treated as busy", () => {
  assert.equal(isBackendPollBusy({ status: "ready" }), false);
  assert.equal(isBackendPollBusy("busy"), false);
  assert.equal(isBackendPollBusy(null), false);
});
