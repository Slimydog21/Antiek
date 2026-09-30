/** Small auth bridge: importing it must not eagerly load the writing surface. */
interface ProseOwner {
  owner: string | null;
  epoch: number;
  suspended: boolean;
}
let state: ProseOwner = { owner: null, epoch: 0, suspended: false };
const listeners = new Set<() => void>();
export const getSectionProseOwner = (): ProseOwner => state;
export function subscribeSectionProseOwner(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function setSectionProseOwner(owner: string | null): void {
  if (state.owner === owner && !state.suspended) return;
  state = { owner, epoch: state.epoch + (state.owner === owner ? 0 : 1), suspended: false };
  for (const listener of listeners) listener();
}
export function suspendSectionProseDispatch(): void {
  if (state.suspended) return;
  state = { ...state, suspended: true };
  for (const listener of listeners) listener();
}
