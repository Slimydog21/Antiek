/**
 * chunkLoadRecovery — survive a deploy that replaced the hashed chunks
 * (FFX SPR-01 M2, client half of P-05; the root boundary is F-01).
 *
 * A tab opened before a deploy still references /assets/Settings-<old>.js.
 * After the deploy that file is gone; on antiek.ai the edge answers the miss
 * with the SPA HTML and `cache-control: immutable` (P-05), so the dynamic
 * import fails and — before this module — the whole root unmounted. Every
 * lazy route goes through Vite's preload helper, which dispatches a
 * cancelable `vite:preloadError` on window (event.payload = the error) and
 * rethrows unless the event is default-prevented.
 *
 * Policy: reload ONCE per failed asset URL. A reload fetches the new
 * index.html, whose chunk names are current, so a stale tab recovers without
 * the user doing anything. If the same URL fails again after that reload,
 * the asset is truly missing (or the edge is serving a cached miss); another
 * reload would loop forever, so we record the failure and let the error
 * reach the root boundary, which says "A new version of Antiek was deployed.
 * Reload to continue." and offers a manual Reload.
 *
 * Why the guard is keyed by asset URL in sessionStorage (not localStorage):
 *   - sessionStorage is per tab. A NEW tab must get its own fresh automatic
 *     attempt — by then the edge cache may have cleared, and a guard set in
 *     some other tab an hour ago would otherwise suppress a reload that would
 *     now work. localStorage would leak the guard across tabs and forever.
 *   - It survives location.reload() in the same tab, which is exactly the
 *     span the loop guard has to cover.
 *   - Keyed by URL (not a single boolean) so a second, unrelated stale chunk
 *     later in the same session still gets its one automatic attempt.
 *   - If storage cannot hold the guard (private mode quota, blocked storage)
 *     we do NOT reload: without a guard a missing asset would reload forever,
 *     and a boundary message is strictly better than a reload loop.
 *
 * We never call event.preventDefault(): the error must still reject the lazy
 * import so React routes it to the boundary. On the first-failure path the
 * boundary may paint for a frame before the reload lands; that copy is true.
 */

const GUARD_PREFIX = "antiek:chunk-reload:";

export function chunkReloadGuardKey(url: string): string {
  return `${GUARD_PREFIX}${url}`;
}

const CHUNK_ERROR_PATTERNS: readonly RegExp[] = [
  /Failed to fetch dynamically imported module/i, // Chromium
  /error loading dynamically imported module/i, // Firefox
  /Importing a module script failed/i, // Safari (no URL in the message)
  /Unable to preload CSS for/i, // Vite's own CSS preload failure
  /Loading (CSS )?chunk \S+ failed/i, // legacy bundler wording
];

function messageOf(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return "";
}

/** True when an error is a failed chunk / CSS download, not an app bug. */
export function isChunkLoadError(err: unknown): boolean {
  const message = messageOf(err);
  return message !== "" && CHUNK_ERROR_PATTERNS.some((re) => re.test(message));
}

function currentPathname(): string {
  try {
    return window.location?.pathname || "/";
  } catch {
    return "/";
  }
}

/**
 * The asset URL named in a chunk-load error. Safari's message carries no URL,
 * so that case is keyed by route: each route still gets exactly one attempt.
 */
export function failedAssetUrl(err: unknown): string {
  const message = messageOf(err);
  const absolute = message.match(/https?:\/\/[^\s'"]+/);
  if (absolute) return absolute[0];
  const rooted = message.match(/\/[^\s'"]*\.(?:m?js|css)\b/);
  if (rooted) return rooted[0];
  return `unknown-asset@${currentPathname()}`;
}

export interface ChunkLoadFailure {
  url: string;
}

let lastFailure: ChunkLoadFailure | null = null;

/** The failure the handler declined to auto-reload for (read by the boundary). */
export function getChunkLoadFailure(): ChunkLoadFailure | null {
  return lastFailure;
}

/** Claim the one automatic attempt for `url`. False when it is spent or unguardable. */
function claimReloadAttempt(url: string): boolean {
  const key = chunkReloadGuardKey(url);
  try {
    const storage = window.sessionStorage;
    if (storage.getItem(key) !== null) return false;
    storage.setItem(key, String(Date.now()));
    // Only reload if the guard demonstrably persisted.
    return storage.getItem(key) !== null;
  } catch {
    return false;
  }
}

function onPreloadError(event: Event): void {
  const payload = (event as Event & { payload?: unknown }).payload;
  const url = failedAssetUrl(payload);
  if (claimReloadAttempt(url)) {
    try {
      window.location.reload();
      return;
    } catch {
      // Fall through: the boundary will offer a manual reload.
    }
  }
  lastFailure = { url };
}

/** Outstanding installs. The listener is attached once, at 0 → 1. */
let installs = 0;

/**
 * Register the handler. Call from main.tsx before the first render.
 *
 * Idempotent and ref-counted (critic F-06): installing twice attaches ONE
 * listener, and every call returns a real uninstaller. The listener is
 * removed when the last outstanding install is released; calling the same
 * uninstaller twice releases only once, so it cannot drop another caller's
 * install.
 */
export function installChunkLoadRecovery(): () => void {
  if (typeof window === "undefined") return () => {};
  installs += 1;
  if (installs === 1) window.addEventListener("vite:preloadError", onPreloadError);
  let released = false;
  return () => {
    if (released) return;
    released = true;
    installs -= 1;
    if (installs === 0) window.removeEventListener("vite:preloadError", onPreloadError);
  };
}

/** Test seam: forget the recorded failure. */
export function __resetChunkLoadRecoveryForTests(): void {
  lastFailure = null;
}
