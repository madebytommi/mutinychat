/** @param {unknown} payload */
export function isBackendPollBusy(payload) {
  return Boolean(
    payload &&
      typeof payload === "object" &&
      !Array.isArray(payload) &&
      /** @type {Record<string, unknown>} */ (payload).status === "busy"
  );
}
