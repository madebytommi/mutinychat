export const INVITATION_CLIPBOARD_TTL_MS = 60_000;

/**
 * Remove an invitation only when it is still the current clipboard value.
 * This avoids overwriting unrelated content the user copied afterward.
 *
 * @param {{ readText?: () => Promise<string>, writeText?: (value: string) => Promise<void> } | null | undefined} clipboard
 * @param {string} invitation
 */
export async function clearInvitationFromClipboard(clipboard, invitation) {
  const expected = String(invitation || "");
  if (!expected || !clipboard?.readText || !clipboard?.writeText) return false;

  try {
    if ((await clipboard.readText()) !== expected) return false;
    await clipboard.writeText("");
    return true;
  } catch {
    return false;
  }
}

/**
 * @param {{ writeText?: (value: string) => Promise<void> } | null | undefined} clipboard
 * @param {string} invitation
 */
export async function writeInvitationToClipboard(clipboard, invitation) {
  const value = String(invitation || "");
  if (!value) throw new Error("No active room invitation is available");
  if (!clipboard?.writeText) throw new Error("Clipboard access is unavailable");
  await clipboard.writeText(value);
  return value;
}
