import { useSyncExternalStore } from "react";

/**
 * Whether the keymap prefix is armed: the one bit of state the dispatcher
 * (workspace/shortcuts.ts) writes and the "prefix armed" chip reads. There is
 * no timer: the prefix stays armed until the next key or Esc.
 */
let armed = false;
const listeners = new Set<() => void>();

function set(next: boolean): void {
  if (armed === next) return;
  armed = next;
  for (const fn of listeners) fn();
}

export const prefixState = {
  isArmed: (): boolean => armed,
  arm: (): void => set(true),
  disarm: (): void => set(false),
  subscribe(fn: () => void): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

export function usePrefixArmed(): boolean {
  return useSyncExternalStore(prefixState.subscribe, prefixState.isArmed, () => false);
}
