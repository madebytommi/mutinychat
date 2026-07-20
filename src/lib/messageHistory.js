export const MAX_CHAT_MESSAGE_BYTES = 16 * 1024;
export const MAX_POLL_MESSAGES = 32;
export const MAX_RENDERED_MESSAGES = 200;
export const MAX_RENDERED_MESSAGE_CHARS = 256 * 1024;

/** @param {unknown} value */
export function utf8ByteLength(value) {
  return new TextEncoder().encode(String(value)).length;
}

/** @param {{ text?: unknown, sender?: unknown }} message */
function renderedCharacterCount(message) {
  return String(message.text ?? "").length + String(message.sender ?? "").length;
}

/**
 * @template {{ text: string, sender?: string }} T
 * @param {T[]} current
 * @param {T[]} additions
 */
export function appendBoundedMessages(current, additions) {
  const accepted = [];
  let rejectedCount = 0;

  for (const addition of additions) {
    const text = String(addition?.text ?? "");
    if (!text || utf8ByteLength(text) > MAX_CHAT_MESSAGE_BYTES) {
      rejectedCount += 1;
      continue;
    }
    accepted.push(/** @type {T} */ ({ ...addition, text }));
  }

  const combined = [...current, ...accepted];
  let renderedCharacters = combined.reduce(
    (total, message) => total + renderedCharacterCount(message),
    0
  );
  let firstRetainedIndex = 0;

  while (
    combined.length - firstRetainedIndex > MAX_RENDERED_MESSAGES ||
    renderedCharacters > MAX_RENDERED_MESSAGE_CHARS
  ) {
    renderedCharacters -= renderedCharacterCount(combined[firstRetainedIndex]);
    firstRetainedIndex += 1;
  }

  return {
    messages: combined.slice(firstRetainedIndex),
    removedCount: firstRetainedIndex,
    rejectedCount
  };
}
