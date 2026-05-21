// User-settings store for the reading surface (SPR-04 M1).
//
// Wave-2 surface-side settings. Persistence is localStorage today; a
// substrate-backed `user_settings` table replaces it when the REST
// endpoint lands (see migrations/reading_mode.sql). The shape on disk
// is intentionally a flat JSON object so the SQL row can be a single
// JSONB column without further translation work.
//
// IMPORTANT: this is the ONLY settings module Wave-2 surfaces should
// import. If a future sprint needs a new setting, add a field below
// and a default in DEFAULTS — do NOT spawn a parallel store.
//
// Reads are synchronous + side-effect-free (safe to call during render).
// Writes go through `updateUserSettings(...)` which fans out to all
// registered subscribers — components subscribe via `useUserSettings()`.
//
// localStorage failures (private-mode browsers, quota) are non-fatal:
// the in-memory copy still serves reads; writes silently no-op on the
// disk side. Matches the posture of `useInvestigationTree`.
//
// SPR-04 M1 — defaults for new vs existing users:
//
//   - New users           → reading_mode = 'reader'
//   - Existing users      → reading_mode = 'researcher'
//
// "New" is determined by the absence of any persisted settings row at
// load time. "Existing" means the user had a prior session before
// SPR-04 landed (no `reading_mode` field on the persisted object).
// Rationale lives in migrations/reading_mode.sql §Why; the short
// version: dual-market positioning. The cozy reader is the consumer
// wedge; existing researchers should not get yanked into a calmer UI
// without consent. Defensibility rigor #5 on the SPR-04 sprint page.
//
// Do NOT "fix" the default to 'researcher' for everyone without
// re-reading the rationale. A future maintainer might assume the
// asymmetry is a bug.

const STORAGE_KEY = "antiek.user_settings.v1";

// Sentinel that distinguishes "never persisted" from "persisted with
// an older shape that lacks reading_mode". The migration in
// `migrations/reading_mode.sql` mirrors this discriminator.
const PERSISTED_FLAG = "__persisted__";

export type ReadingMode = "researcher" | "reader";

export interface UserSettings {
  reading_mode: ReadingMode;
  // Discriminator for the new/existing distinction. Older persisted
  // objects (pre-SPR-04) do NOT have this — they only have whatever
  // fields existed at the time. Reading the persisted shape via the
  // safe-parser fills in `reading_mode` accordingly.
  [PERSISTED_FLAG]?: true;
}

const DEFAULTS_NEW_USER: UserSettings = {
  reading_mode: "reader",
  [PERSISTED_FLAG]: true,
};

const DEFAULT_EXISTING_USER_READING_MODE: ReadingMode = "researcher";

type Subscriber = (next: UserSettings) => void;

let cache: UserSettings | null = null;
const subscribers = new Set<Subscriber>();

function safeLocalStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Load settings from disk, applying the new-vs-existing default rule.
 *
 *   - No persisted row at all → DEFAULTS_NEW_USER (reading_mode = 'reader').
 *   - Persisted row, has reading_mode → use it.
 *   - Persisted row, no reading_mode → set reading_mode to
 *     DEFAULT_EXISTING_USER_READING_MODE ('researcher'). This is the
 *     migration case: the user existed pre-SPR-04 and should stay in
 *     researcher mode until they opt into reader mode themselves.
 */
function loadFromStorage(): UserSettings {
  const ls = safeLocalStorage();
  if (!ls) return { ...DEFAULTS_NEW_USER };

  const raw = ls.getItem(STORAGE_KEY);
  if (!raw) {
    // Truly new user — no settings row exists. Default to reader.
    return { ...DEFAULTS_NEW_USER };
  }

  try {
    const parsed = JSON.parse(raw) as Partial<UserSettings>;
    // Existing user: the row exists but predates SPR-04. The
    // `reading_mode` field is absent. Migrate them to 'researcher'.
    if (parsed.reading_mode !== "researcher" && parsed.reading_mode !== "reader") {
      return {
        ...parsed,
        reading_mode: DEFAULT_EXISTING_USER_READING_MODE,
        [PERSISTED_FLAG]: true,
      };
    }
    return {
      ...parsed,
      reading_mode: parsed.reading_mode,
      [PERSISTED_FLAG]: true,
    };
  } catch {
    // Corrupted row — treat as new user. Don't lose data destructively;
    // a backup is not needed because the only field today IS reading_mode.
    return { ...DEFAULTS_NEW_USER };
  }
}

function writeToStorage(next: UserSettings): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  try {
    ls.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Quota / private-mode failure. In-memory cache still serves reads
    // for the rest of the session.
  }
}

/** Synchronous read. Idempotent and safe during render. */
export function getUserSettings(): UserSettings {
  if (cache === null) {
    cache = loadFromStorage();
  }
  return cache;
}

/** Patch one or more fields. Persists, then notifies subscribers. */
export function updateUserSettings(patch: Partial<UserSettings>): UserSettings {
  const current = getUserSettings();
  const next: UserSettings = { ...current, ...patch, [PERSISTED_FLAG]: true };
  cache = next;
  writeToStorage(next);
  for (const s of subscribers) {
    try {
      s(next);
    } catch {
      // Subscriber errors must not break sibling subscribers.
    }
  }
  return next;
}

/** Subscribe to changes. Returns an unsubscribe handle. */
export function subscribeUserSettings(fn: Subscriber): () => void {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
}

/**
 * Reset all in-memory + disk state. Test-only entry point — keeps the
 * production module deterministic across vitest cases.
 */
export function __resetUserSettingsForTests(): void {
  cache = null;
  subscribers.clear();
  const ls = safeLocalStorage();
  if (ls) {
    try {
      ls.removeItem(STORAGE_KEY);
    } catch {
      // ignored
    }
  }
}

/**
 * Test-only: pre-seed a persisted row to simulate an "existing user"
 * who predates SPR-04 (has a settings row but no reading_mode field).
 */
export function __seedExistingUserPreSpr04ForTests(): void {
  const ls = safeLocalStorage();
  cache = null;
  if (ls) {
    try {
      // Intentionally write a row that lacks reading_mode.
      ls.setItem(STORAGE_KEY, JSON.stringify({ [PERSISTED_FLAG]: true }));
    } catch {
      // ignored
    }
  }
}
