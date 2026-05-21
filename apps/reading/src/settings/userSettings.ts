// SPR-06 / M4 — User settings store (client-side).
//
// The substrate doesn't yet carry a per-user settings table; the
// backend `last_session_at` field that the sprint spec referenced
// doesn't exist either. We use localStorage as the source of truth
// for these consumer-surface preferences, namespaced under
// `antiek.userSettings.v1`. A future sprint can mirror these into
// a server-side store without breaking the read/write API below
// (the swap is in this file only).
//
// The "alwaysStartAtLibrary" flag interacts with `routing/postLogin.ts`:
//   - new users (no last-opened-doc on this device) default to TRUE
//   - existing users (have a last-opened-doc) default to FALSE
//   - either user can flip the setting once they discover the toggle
// The default is read at post-login time, so flipping the setting
// applies to the NEXT login (not the current session).
//
// "lastOpenedDocumentId" is the device-local proxy for "this user has
// done something here before." We do NOT call them a returning user
// based on auth identity (the auth system doesn't expose
// last_session_at) — we use the existence of localStorage state as
// a proxy. This is honest about the limitation: the same user on a
// new device will be treated as a new user. Per rigor #1, the
// handoff calls this out.

const SETTINGS_KEY = "antiek.userSettings.v1";
const LAST_OPENED_KEY = "antiek.lastOpenedDocumentId.v1";

export interface UserSettings {
  /** Toggle for "after login, send me to /library instead of my
   * last-opened document." Default is set per-user on first observation
   * (see {@link inferDefaultAlwaysStartAtLibrary}). */
  alwaysStartAtLibrary: boolean | null;
}

const DEFAULT_SETTINGS: UserSettings = {
  alwaysStartAtLibrary: null,
};

/** Read user settings from localStorage. Missing keys fill in with
 * `null` so {@link inferDefaultAlwaysStartAtLibrary} can decide
 * dynamically at post-login. */
export function readUserSettings(): UserSettings {
  if (typeof window === "undefined" || !window.localStorage) {
    return { ...DEFAULT_SETTINGS };
  }
  const raw = window.localStorage.getItem(SETTINGS_KEY);
  if (!raw) return { ...DEFAULT_SETTINGS };
  try {
    const parsed = JSON.parse(raw) as Partial<UserSettings>;
    return {
      alwaysStartAtLibrary:
        typeof parsed.alwaysStartAtLibrary === "boolean"
          ? parsed.alwaysStartAtLibrary
          : null,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/** Persist settings. Shallow-merges with whatever's in storage. */
export function writeUserSettings(patch: Partial<UserSettings>): UserSettings {
  const current = readUserSettings();
  const next = { ...current, ...patch };
  if (typeof window !== "undefined" && window.localStorage) {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  }
  return next;
}

/** Record that the user has just opened a document. Called by the
 * Wrestle reader (and by LibraryGrid card click) so the next login's
 * post-login routing has a sensible "last doc" to fall back to. */
export function recordLastOpenedDocument(documentId: string): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  if (!documentId) return;
  window.localStorage.setItem(LAST_OPENED_KEY, documentId);
}

/** Read the last-opened document id from this device, or null. */
export function readLastOpenedDocument(): string | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  return window.localStorage.getItem(LAST_OPENED_KEY);
}

/** Compute the default for "always start at library" for a user we
 * haven't asked yet. New users (no last-opened doc) → true (consumer
 * wedge landing). Existing users (have a last-opened doc) → false
 * (keep them where they were). */
export function inferDefaultAlwaysStartAtLibrary(): boolean {
  return readLastOpenedDocument() === null;
}

/** Effective value of "always start at library": user-set if set,
 * otherwise inferred default. */
export function effectiveAlwaysStartAtLibrary(): boolean {
  const settings = readUserSettings();
  if (settings.alwaysStartAtLibrary === null) {
    return inferDefaultAlwaysStartAtLibrary();
  }
  return settings.alwaysStartAtLibrary;
}

/** TEST/DEV ONLY — wipe user settings + last-opened. */
export function _resetUserSettingsForTests(): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.removeItem(SETTINGS_KEY);
  window.localStorage.removeItem(LAST_OPENED_KEY);
}
