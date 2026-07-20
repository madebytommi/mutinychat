import {
  appendBoundedMessages,
  MAX_CHAT_MESSAGE_BYTES,
  MAX_RENDERED_MESSAGE_CHARS,
  MAX_RENDERED_MESSAGES,
  utf8ByteLength
} from "../../src/lib/messageHistory.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  },
  /** @param {unknown} value */
  ok(value) {
    if (!value) throw new Error(`Expected a truthy value, received ${String(value)}`);
  }
};

/** @param {string} name @param {() => void} run */
function test(name, run) {
  run();
  console.log(`ok - ${name}`);
}

/** @param {number} id @param {string} text */
function message(id, text) {
  return { id, text, isMine: false, sender: "Peer" };
}

test("UTF-8 byte accounting handles multibyte text", () => {
  assert.equal(utf8ByteLength("a"), 1);
  assert.equal(utf8ByteLength("é"), 2);
  assert.equal(utf8ByteLength("😀"), 4);
});

test("message at the byte limit is retained", () => {
  const result = appendBoundedMessages([], [message(1, "a".repeat(MAX_CHAT_MESSAGE_BYTES))]);

  assert.equal(result.rejectedCount, 0);
  assert.equal(result.messages.length, 1);
});

test("oversized individual message is rejected", () => {
  const result = appendBoundedMessages([], [
    message(1, "é".repeat(MAX_CHAT_MESSAGE_BYTES / 2 + 1))
  ]);

  assert.equal(result.rejectedCount, 1);
  assert.equal(result.messages.length, 0);
});

test("history retains only the newest message-count window", () => {
  const additions = Array.from({ length: MAX_RENDERED_MESSAGES + 5 }, (_, index) =>
    message(index, `message-${index}`)
  );
  const result = appendBoundedMessages([], additions);

  assert.equal(result.messages.length, MAX_RENDERED_MESSAGES);
  assert.equal(result.removedCount, 5);
  assert.equal(result.messages[0].id, 5);
  assert.equal(result.messages.at(-1)?.id, MAX_RENDERED_MESSAGES + 4);
});

test("history enforces the aggregate rendered-character budget", () => {
  const additions = Array.from({ length: 20 }, (_, index) =>
    message(index, "x".repeat(16_000))
  );
  const result = appendBoundedMessages([], additions);
  const retainedCharacters = result.messages.reduce(
    (total, item) => total + item.text.length + item.sender.length,
    0
  );

  assert.ok(result.removedCount > 0);
  assert.ok(retainedCharacters <= MAX_RENDERED_MESSAGE_CHARS);
  assert.equal(result.messages.at(-1)?.id, 19);
});

test("repeated additions remain bounded", () => {
  /** @type {ReturnType<typeof message>[]} */
  let history = [];
  let removed = 0;
  for (let index = 0; index < MAX_RENDERED_MESSAGES * 3; index += 1) {
    const result = appendBoundedMessages(history, [message(index, `message-${index}`)]);
    history = result.messages;
    removed += result.removedCount;
  }

  assert.equal(history.length, MAX_RENDERED_MESSAGES);
  assert.equal(removed, MAX_RENDERED_MESSAGES * 2);
  assert.equal(history[0].id, MAX_RENDERED_MESSAGES * 2);
});
