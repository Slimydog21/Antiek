/** Small auth bridge: importing it must not eagerly load the tab store. */
interface TabOwner {
  owner: string | null;
  epoch: number;
  suspended: boolean;
}
let state: TabOwner = { owner: null, epoch: 0, suspended: false };
const listeners = new Set<() => void>();
export const getTabOwner = (): TabOwner => state;
export function subscribeTabOwner(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function setTabOwner(owner: string | null): void {
  if (state.owner === owner && !state.suspended) return;
  state = { owner, epoch: state.epoch + (state.owner === owner ? 0 : 1), suspended: false };
  for (const listener of listeners) listener();
}
export function suspendTabDispatch(): void {
  if (state.suspended) return;
  state = { ...state, suspended: true };
  for (const listener of listeners) listener();
}
