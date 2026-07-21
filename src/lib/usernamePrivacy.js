export const LEGACY_USERNAME_PREF_KEY = "mutinychat-username";

/**
 * @param {{ removeItem: (key: string) => void } | null | undefined} storage
 * @returns {boolean}
 */
export function clearLegacyUsernamePreference(storage) {
  if (!storage) return false;
  try {
    storage.removeItem(LEGACY_USERNAME_PREF_KEY);
    return true;
  } catch {
    return false;
  }
}
