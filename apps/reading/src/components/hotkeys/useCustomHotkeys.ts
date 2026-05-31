import { useCallback, useEffect, useState } from "react";

import {
  type PersistedCustomHotkey,
  readCustomHotkeys,
  writeCustomHotkeys,
  clearCustomHotkeys,
} from "../../workspace/persistence";
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
const liveListeners = new Set<() => void>();
function notifyCustomHotkeysChanged() {
  for (const fn of liveListeners) fn();
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
  const [bindings, setBindings] = useState<PersistedCustomHotkey[]>(
    () => readCustomHotkeys().bindings,
  );

  // Whenever the React map changes, persist + push the resolvable subset to
  // the live keydown handler so presses fire without a remount, then signal
  // sibling instances so they re-read (same-tab liveness).
  useEffect(() => {
    writeCustomHotkeys({ schemaVersion: 1, bindings });
    setCustomHotkeys(
      bindings.map((b) => ({
        id: b.id,
        spec: b.spec,
        route: b.route,
        entityId: b.entityId,
      })),
    );
    notifyCustomHotkeysChanged();
  }, [bindings]);

  // Stay live across sibling instances (same-tab pub-sub) and other tabs
  // (the `storage` event). On any signal, re-read the canonical blob — this is
  // idempotent for the writer (it just wrote the same value) and corrects a
  // stale sibling. The push to the keydown handler is driven by the effect
  // above when this re-read actually changes our state.
  useEffect(() => {
    // Re-read, but bail if the persisted value already matches our state — so
    // the instance that JUST wrote (and triggered the notify) doesn't loop:
    // its re-read is value-equal, the functional update returns `prev`, and the
    // `[bindings]` effect doesn't re-run.
    const sync = () =>
      setBindings((prev) => {
        const next = readCustomHotkeys().bindings;
        return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
    liveListeners.add(sync);
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key.endsWith("custom-hotkeys")) sync();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      liveListeners.delete(sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const bindingForEntity = useCallback(
    (entityId: string) => bindings.find((b) => b.entityId === entityId),
    [bindings],
  );

  const checkConflict = useCallback(
    (spec: string, selfId?: string): Conflict | null =>
      detectConflict(
        spec,
        bindings.map((b) => ({ id: b.id, spec: b.spec })),
        selfId,
      ),
    [bindings],
  );

  const assign = useCallback(
    (input: CustomHotkeyInput, force = false): AssignResult => {
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
      const existing = bindings.find((b) => b.entityId === input.entityId);
      const conflict = detectConflict(
        spec,
        bindings.map((b) => ({ id: b.id, spec: b.spec })),
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

      setBindings((prev) => {
        // Drop: (a) any other binding holding this spec (override), and
        // (b) this entity's previous binding (re-bind).
        const cleaned = prev.filter(
          (b) =>
            normalizeBinding(b.spec) !== spec && b.entityId !== input.entityId,
        );
        return [...cleaned, binding];
      });

      return { ok: true, conflict, binding };
    },
    [bindings],
  );

  const removeForEntity = useCallback((entityId: string) => {
    setBindings((prev) => prev.filter((b) => b.entityId !== entityId));
  }, []);

  const removeById = useCallback((id: string) => {
    setBindings((prev) => prev.filter((b) => b.id !== id));
  }, []);

  const resetAll = useCallback(() => {
    clearCustomHotkeys();
    setBindings([]);
  }, []);

  return {
    bindings,
    bindingForEntity,
    checkConflict,
    assign,
    removeForEntity,
    removeById,
    resetAll,
  };
}
