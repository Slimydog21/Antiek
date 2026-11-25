/**
 * agents/statusToastFlag.ts — ENTRY-SAFE (no imports). Whether a status
 * toast is on screen, kept apart from statusToasts.ts (lazy: it pulls the
 * store and companionStore) so the keymap dispatcher can answer
 * agents.gotoToast synchronously: with nothing visible the key is not ours
 * and falls through to the browser (KeyHandler's `false`).
 */
let visible = false;

export function statusToastVisible(): boolean {
  return visible;
}

export function setStatusToastVisible(v: boolean): void {
  visible = v;
}
