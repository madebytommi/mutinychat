import {
  LEGACY_USERNAME_PREF_KEY,
  clearLegacyUsernamePreference
} from "../../src/lib/usernamePrivacy.js";

/** @type {string[]} */
const removedKeys = [];
const storage = {
  /** @param {string} key */
  removeItem(key) {
    removedKeys.push(key);
  }
};

if (!clearLegacyUsernamePreference(storage)) {
  throw new Error("Expected legacy username cleanup to succeed");
}
if (JSON.stringify(removedKeys) !== JSON.stringify([LEGACY_USERNAME_PREF_KEY])) {
  throw new Error("Expected only the legacy username preference to be removed");
}
if (clearLegacyUsernamePreference(null)) {
  throw new Error("Unavailable storage must fail safely");
}
if (
  clearLegacyUsernamePreference({
    removeItem() {
      throw new Error("storage denied");
    }
  })
) {
  throw new Error("Storage failures must be contained");
}

console.log("username privacy frontend tests passed");
