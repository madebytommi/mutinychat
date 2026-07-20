import {
  INVITATION_CLIPBOARD_TTL_MS,
  clearInvitationFromClipboard,
  writeInvitationToClipboard
} from "../../src/lib/invitationClipboard.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  },
  /** @param {unknown} actual @param {unknown} expected */
  deepEqual(actual, expected) {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      throw new Error(`Expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
    }
  },
  /** @param {Promise<unknown>} promise @param {RegExp} pattern */
  async rejects(promise, pattern) {
    try {
      await promise;
    } catch (error) {
      if (pattern.test(String(error))) return;
      throw new Error(`Unexpected rejection: ${String(error)}`);
    }
    throw new Error("Expected promise to reject");
  }
};

assert.equal(INVITATION_CLIPBOARD_TTL_MS, 60_000);

/** @type {string[]} */
const writes = [];
const clipboard = {
  value: "",
  async readText() {
    return this.value;
  },
  /** @param {string} value */
  async writeText(value) {
    this.value = value;
    writes.push(value);
  }
};

const invitation = "mutinychat://join?onion=example.onion&key=secret-capability";
assert.equal(await writeInvitationToClipboard(clipboard, invitation), invitation);
assert.equal(clipboard.value, invitation);
assert.equal(await clearInvitationFromClipboard(clipboard, invitation), true);
assert.equal(clipboard.value, "");
assert.deepEqual(writes, [invitation, ""]);

clipboard.value = "new unrelated clipboard content";
assert.equal(await clearInvitationFromClipboard(clipboard, invitation), false);
assert.equal(clipboard.value, "new unrelated clipboard content");

assert.equal(await clearInvitationFromClipboard(null, invitation), false);
await assert.rejects(
  writeInvitationToClipboard(null, invitation),
  /Clipboard access is unavailable/
);
await assert.rejects(writeInvitationToClipboard(clipboard, ""), /No active room invitation/);

console.log("invitationClipboard frontend tests passed");
