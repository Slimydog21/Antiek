import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  type PersistedCustomHotkey,
  readCustomHotkeys,
  writeCustomHotkeys,
  clearCustomHotkeys,
} from "../../workspace/persistence";
import {
  accountStorageKey, awaitWorkspaceOwnerSession, isWorkspaceOwnerSession,
  subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, workspaceOwnerSession,
  type WorkspaceOwnerSession,
} from "../../lib/accountWorkspaceOwner";
import { setCustomHotkeys } from "../../workspace/shortcuts";
import {
  type Conflict,
  detectConflict,
  isBlockingConflict,
  normalizeBinding,
  requiresModifierReason,
  SAFE_ASSIGNABLE,
} from "./bindings";

/**
 * useCustomHotkeys — SPR-08 (milestones 4 + 5).
 *
 * Owns the persisted map of USER-SETTABLE per-entity hotkeys: a hotkey
 * bound to ONE specific investigation / book / writing deliverable / speak
 * project. The map is persisted as a separate, versioned global blob (see
 * `persistence.ts` `readCustomHotkeys` / `writeCustomHotkeys`) and is pushed
 * into the live keydown handler via `setCustomHotkeys` so a press navigates
 * to the entity — interchangeable with clicking it (the activation event is
 * emitted by the handler).
 *
 * The hook is the SINGLE source of truth in React for the custom map; the
 * imperative handler in `shortcuts.ts` mirrors it. Whenever the map changes
 * we (a) persist it and (b) re-push the resolvable subset to the handler.
 *
 * Conflict + precedence (rigor #3, documented in `bindings.ts`):
 *   - custom CANNOT shadow a built-in / product / sub-action → blocked.
 *   - custom-vs-custom → overridable (last-write-wins, old one dropped).
 *   - reserved browser/OS combo → blocked.
 */
export interface CustomHotkeyInput {
  spec: string;
  route: string;
  entityId: string;
  entityKind: PersistedCustomHotkey["entityKind"];
  label: string;
}

export interface AssignResult {
  ok: boolean;
  /** The conflict that blocked, or that was overridden (for messaging). */
  conflict: Conflict | null;
  /** The resulting binding when ok. */
  binding?: PersistedCustomHotkey;
}

// ─────────────────────────────────────────────────────────────────────
// Cross-instance liveness — SPR-08 sharpen
// ─────────────────────────────────────────────────────────────────────
//
// Multiple <AssignHotkey> surfaces can be mounted at once (e.g. one per
// research card), each holding its own React mirror of the single persisted
// blob. Without a shared signal, an assign in one wouldn't update its siblings
// until they remount. We use a tiny in-process pub-sub (same-tab) plus the
// `storage` window event (cross-tab) — NOT a full Zustand migration, which
// would be gold-plating for one low-churn global blob. On notify, every hook
// re-reads the canonical blob from persistence.
//
// Persistence-migration policy (documented decision): the custom-hotkeys blob
// is a single low-value global record. A vN→vN+1 schema bump is "discard +
// reset", not a data migration — `readCustomHotkeys` already returns an empty
// v1 envelope on a version mismatch (see persistence.ts). We accept that
// trade deliberately: the cost of writing/maintaining a migration outweighs
// re-binding a handful of personal hotkeys.
const noBindings: PersistedCustomHotkey[] = [];
const liveListeners = new Set<() => void>();
function notifyCustomHotkeysChanged(owner: WorkspaceOwnerSession) {
  for (const fn of liveListeners) {
    if (!isWorkspaceOwnerSession(owner)) return;
    fn();
  }
}

let nextIdCounter = 0;
function makeId(): string {
  nextIdCounter += 1;
  const rand =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${nextIdCounter}`;
  return `ckb-${rand}`;
}

export interface UseCustomHotkeys {
  bindings: PersistedCustomHotkey[];
  /** The binding currently assigned to an entity, if any. */
  bindingForEntity: (entityId: string) => PersistedCustomHotkey | undefined;
  /** Check (without mutating) what would happen if `spec` were assigned. */
  checkConflict: (spec: string, selfId?: string) => Conflict | null;
  /**
   * Assign (or re-bind) a hotkey to an entity.
   *
   * `force` lets the caller accept an overridable custom-vs-custom conflict;
   * blocking conflicts (built-in / reserved) are ALWAYS rejected regardless
   * of `force`.
   */
  assign: (input: CustomHotkeyInput, force?: boolean) => AssignResult;
  /** Remove the binding for an entity (if any). */
  removeForEntity: (entityId: string) => void;
  /** Remove a binding by its id. */
  removeById: (id: string) => void;
  /** Reset ALL custom hotkeys to defaults (clears the blob). */
  resetAll: () => void;
}

export function useCustomHotkeys(): UseCustomHotkeys {
  const [owner] = useState(workspaceOwnerSession);
  const admission = useSyncExternalStore(
    subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, workspaceOwnerAdmission,
  );
  const live = useRef(true);
  const confirmed = useRef(false);
  const loaded = useRef(false);
  const snapshot = useRef<PersistedCustomHotkey[]>(noBindings);
  const pendingEdit = useRef(false);
  const current = useCallback(() => live.current && confirmed.current
    && owner.subject !== null && isWorkspaceOwnerSession(owner), [owner]);
  const [bindings, setBindings] = useState<PersistedCustomHotkey[]>(noBindings);

  useEffect(() => {
    if (!loaded.current || !current()) return;
    const next = snapshot.current;
    writeCustomHotkeys({ schemaVersion: 1, bindings: next });
    if (!current() || snapshot.current !== next) return;
    setCustomHotkeys(next, owner);
    if (!current() || snapshot.current !== next) return;
    notifyCustomHotkeysChanged(owner);
    if (current() && snapshot.current === next) pendingEdit.current = false;
  }, [bindings, current, owner]);

  useEffect(() => {
    live.current = true;
    confirmed.current = false;
    const controller = new AbortController();
    let generation = 0;
    const sync = () => {
      if (!current()) return;
      if (pendingEdit.current) {
        setBindings([...snapshot.current]);
        return;
      }
      const next = readCustomHotkeys().bindings;
      if (!current()) return;
      const wasLoaded = loaded.current;
      loaded.current = true;
      setCustomHotkeys(next, owner);
      if (!current()) return;
      if (!wasLoaded || JSON.stringify(snapshot.current) !== JSON.stringify(next)) {
        snapshot.current = next;
        setBindings(next);
      }
    };
    const confirm = () => {
      const attempt = ++generation;
      void awaitWorkspaceOwnerSession(owner, controller.signal).then((ready) => {
        if (!live.current || attempt !== generation || !ready || !isWorkspaceOwnerSession(owner)) return;
        confirmed.current = true;
        sync();
      }, () => {
        if (attempt === generation) confirmed.current = false;
      });
    };
    liveListeners.add(sync);
    const storageKey = accountStorageKey("antiek.workspace.custom-hotkeys", owner);
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === storageKey) sync();
    };
    const unsubscribe = subscribeWorkspaceOwnerAdmission((admission) => {
      generation += 1;
      confirmed.current = false;
      if (admission.session !== owner || admission.state === "retiring" || admission.state === "failed") {
        controller.abort();
        loaded.current = false;
        pendingEdit.current = false;
        snapshot.current = noBindings;
        setBindings(noBindings);
        return;
      }
      if (admission.state === "ready") confirm();
    });
    window.addEventListener("storage", onStorage);
    confirm();
    return () => {
      live.current = false;
      confirmed.current = false;
      generation += 1;
      controller.abort();
      liveListeners.delete(sync);
      unsubscribe();
      window.removeEventListener("storage", onStorage);
    };
  }, [current, owner]);

  const accept = useCallback((next: PersistedCustomHotkey[]) => {
    if (!current()) return false;
    snapshot.current = next;
    pendingEdit.current = true;
    setBindings(next);
    return true;
  }, [current]);

  const visibleBindings = admission.session === owner
    && (admission.state === "ready" || admission.state === "suspended") ? bindings : noBindings;

  const bindingForEntity = useCallback(
    (entityId: string) => visibleBindings.find((b) => b.entityId === entityId),
    [visibleBindings],
  );

  const checkConflict = useCallback(
    (spec: string, selfId?: string): Conflict | null =>
      detectConflict(
        spec,
        visibleBindings.map((b) => ({ id: b.id, spec: b.spec })),
        selfId,
      ),
    [visibleBindings],
  );

  const assign = useCallback(
    (input: CustomHotkeyInput, force = false): AssignResult => {
      if (!current()) return { ok: false, conflict: { kind: "reserved", withId: "", message: "The account is not ready for custom hotkey changes." } };
      const spec = normalizeBinding(input.spec);
      // Shape gate (defence-in-depth with the capture affordance): a custom
      // binding must carry a modifier and must not be a chord. We reject a
      // bare key / chord here too so the persisted blob can never hold an
      // unfireable binding even if a caller bypasses the capture dialog.
      const shapeReason = requiresModifierReason(spec);
      if (shapeReason) {
        return {
          ok: false,
          conflict: { kind: "reserved", withId: "", message: shapeReason },
        };
      }
      // SAFE_ASSIGNABLE shape gate — the scheme is ⌘+key ONLY. An ⌥-only
      // (Option) combo passes the modifier check above (it carries a
      // modifier) but is OFF-SPEC: SPR-08's command scheme is a single
      // ⌘+<key>, with no ⌥-prefixed namespace. `isWithinRange` is the live
      // shape gate for that policy (it requires `mod` to be present), so we
      // reject anything outside the safe ⌘ range here, alongside detectConflict
      // (ownership/reserved). Both must pass for an assign to succeed.
      if (!SAFE_ASSIGNABLE.isWithinRange(spec)) {
        return {
          ok: false,
          conflict: {
            kind: "reserved",
            withId: "",
            message:
              "Use ⌘ + a key (Option-only combos aren't assignable) — for example ⌘J.",
          },
        };
      }
      // If this entity already has a binding, re-binding it is allowed
      // (we pass its id as `selfId` so it doesn't conflict with itself).
      const existing = snapshot.current.find((b) => b.entityId === input.entityId);
      const conflict = detectConflict(
        spec,
        snapshot.current.map((b) => ({ id: b.id, spec: b.spec })),
        existing?.id,
      );

      if (conflict && isBlockingConflict(conflict)) {
        return { ok: false, conflict };
      }
      if (conflict && !force) {
        // Overridable custom-vs-custom — caller must confirm with force.
        return { ok: false, conflict };
      }

      const binding: PersistedCustomHotkey = {
        id: existing?.id ?? makeId(),
        spec,
        route: input.route,
        entityId: input.entityId,
        entityKind: input.entityKind,
        label: input.label,
      };

      // Retain an admitted edit before React runs its state update.
      const cleaned = snapshot.current.filter(
        (b) => normalizeBinding(b.spec) !== spec && b.entityId !== input.entityId,
      );
      if (!accept([...cleaned, binding])) return { ok: false, conflict: null };
      return { ok: true, conflict, binding };
    },
    [accept, current],
  );

  const removeForEntity = useCallback((entityId: string) => {
    if (current()) accept(snapshot.current.filter((b) => b.entityId !== entityId));
  }, [accept, current]);

  const removeById = useCallback((id: string) => {
    if (current()) accept(snapshot.current.filter((b) => b.id !== id));
  }, [accept, current]);

  const resetAll = useCallback(() => {
    if (!current()) return;
    clearCustomHotkeys();
    if (current()) accept([]);
  }, [accept, current]);

  return {
    bindings: visibleBindings,
    bindingForEntity,
    checkConflict,
    assign,
    removeForEntity,
    removeById,
    resetAll,
  };
}
