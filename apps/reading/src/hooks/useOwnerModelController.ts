import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { fetchUserModels } from "../api/settingsModels";
import { useAuth } from "../lib/auth";
import type { UserModelRow } from "../api/settingsModels";
import type { UserModelChoice } from "../lib/api";
import type { ReadyModelScope } from "../lib/modelExecutionScope";
export type ModelChoice =
  | Readonly<{ kind: "unselected" }>
  | Readonly<{ kind: "house" }>
  | Readonly<{ kind: "saved"; recordId: string; modelId: string }>
  | Readonly<{
      kind: "unavailable";
      recordId: string;
      modelId: string;
      reason: "record_missing" | "variant_missing" | "row_ineligible";
    }>;
export type InventoryRow = Readonly<Omit<UserModelRow, "model_ids">> & {
  readonly model_ids: readonly string[];
};
export type ModelInventory =
  | Readonly<{ kind: "suspended" }>
  | Readonly<{ kind: "loading"; scope: ReadyModelScope; generation: number }>
  | Readonly<{
      kind: "failed";
      scope: ReadyModelScope;
      generation: number;
      reason: "inventory_unavailable" | "inventory_invalid";
    }>
  | Readonly<{
      kind: "ready";
      scope: ReadyModelScope;
      generation: number;
      rows: readonly InventoryRow[];
    }>;
export type SavedLaunchFields = Readonly<{
  model_choice: Readonly<UserModelChoice>;
  operation_id: string;
}>;
export type PreparedModelLaunch =
  | Readonly<{
      kind: "blocked";
      reason:
        | "identity_suspended"
        | "inventory_not_ready"
        | "selection_required"
        | "selection_unavailable"
        | "house_not_permitted";
    }>
  | Readonly<{ kind: "house"; scope: ReadyModelScope }>
  | Readonly<{
      kind: "saved";
      scope: ReadyModelScope;
      selection: Extract<ModelChoice, { kind: "saved" }>;
      semanticKey: string;
      fields: SavedLaunchFields;
    }>;
export interface OwnerModelController {
  inventory: ModelInventory;
  selection: ModelChoice;
  select(choice: Extract<ModelChoice, { kind: "house" | "saved" }>): void;
  prepareLaunch(input: { semanticKey: string }): PreparedModelLaunch;
  refresh(): Promise<void>;
  isCurrent(
    prepared: Exclude<PreparedModelLaunch, { kind: "blocked" }>,
  ): boolean;
}
export interface OwnerModelControllerOptions {
  operationPrefix: string;
  policy: "strict-owner" | "book-route";
  allowHouse: boolean;
}
const UNSELECTED: ModelChoice = Object.freeze({ kind: "unselected" });
const SUSPENDED: ModelInventory = Object.freeze({ kind: "suspended" });
type ActiveLaunch = Exclude<PreparedModelLaunch, { kind: "blocked" }>;

function eligible(
  row: InventoryRow,
  policy: OwnerModelControllerOptions["policy"],
): boolean {
  if (policy === "book-route") return row.route_eligible;
  return (
    row.enabled &&
    row.key_present &&
    row.registered &&
    row.route_eligible &&
    row.pricing_status === "known" &&
    row.hard_ceiling_eligible &&
    row.execution_status === "executable"
  );
}
function validateSelection(
  choice: ModelChoice,
  rows: readonly InventoryRow[],
  policy: OwnerModelControllerOptions["policy"],
): ModelChoice {
  if (choice.kind !== "saved" && choice.kind !== "unavailable") return choice;
  const row = rows.find((value) => value.id === choice.recordId);
  const reason = !row
    ? "record_missing"
    : !row.model_ids.includes(choice.modelId)
      ? "variant_missing"
      : !eligible(row, policy)
        ? "row_ineligible"
        : null;
  return reason
    ? Object.freeze({
        kind: "unavailable",
        recordId: choice.recordId,
        modelId: choice.modelId,
        reason,
      })
    : Object.freeze({
        kind: "saved",
        recordId: choice.recordId,
        modelId: choice.modelId,
      });
}
function sameIdentity(a: ReadyModelScope, b: ReadyModelScope): boolean {
  return (
    a.identity.user_id === b.identity.user_id &&
    a.identity.email === b.identity.email &&
    a.identity.auth_method === b.identity.auth_method
  );
}

/** Staged successor: parsed inventory and preparation only; no action is dispatched. */
export function useOwnerModelController({
  operationPrefix,
  policy,
  allowHouse,
}: OwnerModelControllerOptions): OwnerModelController {
  const { modelExecution } = useAuth();
  const renderedScope = modelExecution.current;
  const { readCurrent, isCurrent: scopeIsCurrent } = modelExecution;
  const [inventory, setInventory] = useState<ModelInventory>(SUSPENDED);
  const [selection, setSelection] = useState<ModelChoice>(UNSELECTED);
  const inventoryRef = useRef<ModelInventory>(SUSPENDED);
  const choiceRef = useRef<ModelChoice>(UNSELECTED);
  const selectionScopeRef = useRef<ReadyModelScope | null>(null);
  const previousScopeRef = useRef<ReadyModelScope | null>(null);
  const generationRef = useRef(0);
  const mountedRef = useRef(true);
  const optionToken = useMemo(
    () => Object.freeze({ operationPrefix, policy, allowHouse }),
    [operationPrefix, policy, allowHouse],
  );
  const committedOptionsRef = useRef<typeof optionToken | null>(null);
  const bindingRef = useRef<{
    prepared: ActiveLaunch;
    generation: number;
    semanticKey: string;
  } | null>(null);
  const operationRef = useRef<{
    scope: ReadyModelScope;
    recordId: string;
    modelId: string;
    semanticKey: string;
    id: string;
  } | null>(null);

  const publishInventory = useCallback((next: ModelInventory) => {
    inventoryRef.current = next;
    setInventory(next);
  }, []);
  const publishChoice = useCallback(
    (next: ModelChoice, scope: ReadyModelScope) => {
      choiceRef.current = next;
      selectionScopeRef.current = scope;
      setSelection(next);
    },
    [],
  );

  // Publish only committed options. Layout cleanup retires the previous token
  // before consumer layout effects; speculative renders never replace authority.
  useLayoutEffect(() => {
    committedOptionsRef.current = optionToken;
    const snapshot = inventoryRef.current;
    if (snapshot.kind === "ready" && scopeIsCurrent(snapshot.scope)) {
      publishChoice(
        validateSelection(choiceRef.current, snapshot.rows, optionToken.policy),
        snapshot.scope,
      );
    }
    return () => {
      if (committedOptionsRef.current === optionToken) {
        committedOptionsRef.current = null;
        generationRef.current += 1;
        bindingRef.current = null;
        operationRef.current = null;
      }
    };
  }, [optionToken, publishChoice, scopeIsCurrent]);

  const loadInventory = useCallback(async () => {
    if (
      !mountedRef.current ||
      committedOptionsRef.current !== optionToken ||
      renderedScope.kind !== "ready" ||
      !scopeIsCurrent(renderedScope)
    )
      return;
    const generation = ++generationRef.current;
    bindingRef.current = null;
    publishInventory(
      Object.freeze({ kind: "loading", scope: renderedScope, generation }),
    );
    try {
      const response = await fetchUserModels();
      if (
        !mountedRef.current ||
        committedOptionsRef.current !== optionToken ||
        !scopeIsCurrent(renderedScope) ||
        generation !== generationRef.current
      )
        return;
      const rows: readonly InventoryRow[] = Object.freeze(
        response.models.map((row) =>
          Object.freeze({
            ...row,
            model_ids: Object.freeze([
              ...new Set(row.model_ids ?? [row.model_id]),
            ]),
          }),
        ),
      );
      publishChoice(
        validateSelection(choiceRef.current, rows, policy),
        renderedScope,
      );
      publishInventory(
        Object.freeze({
          kind: "ready",
          scope: renderedScope,
          generation,
          rows,
        }),
      );
    } catch (error: unknown) {
      if (
        !mountedRef.current ||
        committedOptionsRef.current !== optionToken ||
        !scopeIsCurrent(renderedScope) ||
        generation !== generationRef.current
      )
        return;
      const reason =
        error instanceof Error &&
        error.message === "Invalid user model inventory response."
          ? "inventory_invalid"
          : "inventory_unavailable";
      publishInventory(
        Object.freeze({
          kind: "failed",
          scope: renderedScope,
          generation,
          reason,
        }),
      );
    }
  }, [
    renderedScope,
    scopeIsCurrent,
    optionToken,
    policy,
    publishChoice,
    publishInventory,
  ]);

  const refresh = useCallback(async () => {
    if (inventoryRef.current !== inventory) return;
    await loadInventory();
  }, [inventory, loadInventory]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      bindingRef.current = null;
      operationRef.current = null;
    };
  }, []);
  useEffect(() => {
    generationRef.current += 1;
    bindingRef.current = null;
    operationRef.current = null;
    if (renderedScope.kind !== "ready" || !scopeIsCurrent(renderedScope)) {
      publishInventory(SUSPENDED);
      return;
    }
    if (
      previousScopeRef.current &&
      !sameIdentity(previousScopeRef.current, renderedScope)
    ) {
      choiceRef.current = UNSELECTED;
      setSelection(UNSELECTED);
    }
    previousScopeRef.current = renderedScope;
    void loadInventory();
  }, [renderedScope, scopeIsCurrent, loadInventory, publishInventory]);

  const readySnapshot = useCallback(() => {
    const latest = inventoryRef.current;
    if (
      !mountedRef.current ||
      committedOptionsRef.current !== optionToken ||
      renderedScope.kind !== "ready" ||
      !scopeIsCurrent(renderedScope)
    )
      return null;
    return latest === inventory &&
      latest.kind === "ready" &&
      latest.scope === renderedScope
      ? latest
      : null;
  }, [renderedScope, scopeIsCurrent, optionToken, inventory]);
  const select = useCallback(
    (choice: Extract<ModelChoice, { kind: "house" | "saved" }>) => {
      const snapshot = readySnapshot();
      if (
        !snapshot ||
        inventory.kind !== "ready" ||
        inventory.generation !== snapshot.generation
      )
        return;
      const copied: ModelChoice =
        choice.kind === "house"
          ? Object.freeze({ kind: "house" })
          : Object.freeze({
              kind: "saved",
              recordId: choice.recordId,
              modelId: choice.modelId,
            });
      const next = validateSelection(copied, snapshot.rows, policy);
      const previous = choiceRef.current;
      const sameChoice =
        previous.kind === next.kind &&
        (previous.kind === "house" ||
          (previous.kind === "saved" &&
            next.kind === "saved" &&
            previous.recordId === next.recordId &&
            previous.modelId === next.modelId));
      if (sameChoice) return;
      bindingRef.current = null;
      operationRef.current = null;
      publishChoice(next, snapshot.scope);
    },
    [readySnapshot, inventory, policy, publishChoice],
  );

  const prepareLaunch = useCallback(
    ({ semanticKey }: { semanticKey: string }): PreparedModelLaunch => {
      const current = readCurrent();
      if (
        renderedScope.kind !== "ready" ||
        current !== renderedScope ||
        !mountedRef.current
      )
        return Object.freeze({ kind: "blocked", reason: "identity_suspended" });
      const snapshot = readySnapshot();
      if (!snapshot)
        return Object.freeze({
          kind: "blocked",
          reason: "inventory_not_ready",
        });
      const choice = choiceRef.current;
      if (choice.kind === "unselected")
        return Object.freeze({ kind: "blocked", reason: "selection_required" });
      if (choice.kind === "unavailable")
        return Object.freeze({
          kind: "blocked",
          reason: "selection_unavailable",
        });
      if (choice.kind === "house" && !allowHouse)
        return Object.freeze({
          kind: "blocked",
          reason: "house_not_permitted",
        });
      if (!semanticKey.trim())
        throw new Error("A complete model launch semantic key is required.");
      if (choice.kind === "house") {
        const previous = bindingRef.current;
        if (
          previous?.prepared.kind === "house" &&
          previous.generation === snapshot.generation &&
          previous.semanticKey === semanticKey
        )
          return previous.prepared;
        const prepared = Object.freeze({
          kind: "house" as const,
          scope: snapshot.scope,
        });
        bindingRef.current = {
          prepared,
          generation: snapshot.generation,
          semanticKey,
        };
        return prepared;
      }
      const previous = operationRef.current;
      if (
        !previous ||
        previous.scope !== snapshot.scope ||
        previous.recordId !== choice.recordId ||
        previous.modelId !== choice.modelId ||
        previous.semanticKey !== semanticKey
      ) {
        operationRef.current = {
          scope: snapshot.scope,
          recordId: choice.recordId,
          modelId: choice.modelId,
          semanticKey,
          id: `${operationPrefix}-${crypto.randomUUID()}`,
        };
        bindingRef.current = null;
      }
      const operation = operationRef.current;
      if (!operation) throw new Error("Model launch preparation failed.");
      if (
        bindingRef.current?.prepared.kind === "saved" &&
        bindingRef.current.generation === snapshot.generation
      )
        return bindingRef.current.prepared;
      const prepared: ActiveLaunch = Object.freeze({
        kind: "saved",
        scope: snapshot.scope,
        selection: choice,
        semanticKey,
        fields: Object.freeze({
          model_choice: Object.freeze({
            authority: "user_model",
            provider_id: choice.recordId,
            model_id: choice.modelId,
          }),
          operation_id: operation.id,
        }),
      });
      bindingRef.current = {
        prepared,
        generation: snapshot.generation,
        semanticKey,
      };
      return prepared;
    },
    [renderedScope, readCurrent, readySnapshot, allowHouse, operationPrefix],
  );
  const isCurrent = useCallback(
    (prepared: ActiveLaunch): boolean => {
      const snapshot = readySnapshot();
      const binding = bindingRef.current;
      if (
        !snapshot ||
        !binding ||
        binding.prepared !== prepared ||
        binding.generation !== snapshot.generation ||
        prepared.scope !== snapshot.scope ||
        selectionScopeRef.current !== snapshot.scope
      )
        return false;
      const choice = choiceRef.current;
      if (prepared.kind === "house")
        return allowHouse && choice.kind === "house";
      return (
        choice.kind === "saved" &&
        choice.recordId === prepared.selection.recordId &&
        choice.modelId === prepared.selection.modelId &&
        operationRef.current?.id === prepared.fields.operation_id &&
        operationRef.current.semanticKey === prepared.semanticKey
      );
    },
    [readySnapshot, allowHouse],
  );

  const observed = readCurrent();
  const visibleInventory =
    inventory.kind !== "suspended" &&
    inventory.scope === observed &&
    observed.kind === "ready"
      ? inventory
      : SUSPENDED;
  const visibleSelection =
    observed.kind === "ready" && selectionScopeRef.current === observed
      ? selection
      : UNSELECTED;
  return {
    inventory: visibleInventory,
    selection: visibleSelection,
    select,
    prepareLaunch,
    refresh,
    isCurrent,
  };
}
