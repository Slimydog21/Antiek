import { useSyncExternalStore } from "react";

type Listener = () => void;

const leases = new Set<symbol>();
const listeners = new Set<Listener>();

function notifyIfBoundaryChanged(wasSuspended: boolean): void {
  if (wasSuspended === isStationInstrumentSuspended()) return;
  for (const listener of listeners) listener();
}

/**
 * Temporarily returns pointer authority to a focused product surface.
 *
 * A lease, rather than a boolean setter, makes overlapping owners teardown-safe:
 * one surface cannot accidentally restore the global instrument while another
 * still owns pointer input. The state is process-local and never persisted.
 */
export function acquireStationInstrumentSuspension(
  owner: string,
): () => void {
  const wasSuspended = isStationInstrumentSuspended();
  const lease = Symbol(owner);
  leases.add(lease);
  notifyIfBoundaryChanged(wasSuspended);

  let released = false;
  return () => {
    if (released) return;
    released = true;
    const wasSuspended = isStationInstrumentSuspended();
    leases.delete(lease);
    notifyIfBoundaryChanged(wasSuspended);
  };
}

export function isStationInstrumentSuspended(): boolean {
  return leases.size > 0;
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useStationInstrumentSuspended(): boolean {
  return useSyncExternalStore(
    subscribe,
    isStationInstrumentSuspended,
    () => false,
  );
}
