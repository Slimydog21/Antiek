import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchUserModels, type UserModelRow } from "../api/settingsModels";
import type { UserModelChoice } from "../lib/api";
import { userModelVariants } from "../lib/userModelVariants";

/**
 * useOwnerModelChoice — "which of my own models drives THIS action", as state.
 *
 * The inventory fetch, the executable filter, the eligibility re-check after a
 * refresh and the idempotency id were already written out longhand inside
 * StartResearch. Every further surface that wants the same control needs the
 * same five pieces, so they live here once and the surfaces mount
 * `ModelUsagePicker` over them. This hook holds NO markup: the picker stays the
 * single rendering of a model choice in the app.
 *
 * Two rules are load-bearing rather than stylistic.
 *
 * `model_choice` and `operation_id` travel together or not at all — the server
 * answers 422 `model_selection_invalid` when it sees one without the other
 * (interfaces/research/api/app.py:2354). `launchFields()` is therefore the only
 * way a caller is meant to reach these fields; it returns both or neither.
 *
 * The id identifies ONE launch of ONE request, not one visit to the dropdown.
 * The server claims idempotency on `operation_id` together with a digest of the
 * request body and the chosen route, and answers 409
 * `owner_model_operation_conflict` when an id comes back with a different
 * digest (app.py:2394 via claim_owner_launch). So `launchFields(launchKey)`
 * takes the content that will be launched: the same content resent keeps its id
 * and replays, while edited content — a retyped name after a failed attempt —
 * mints a new one instead of stranding the surface on a 409 nothing in the UI
 * can clear. Choosing a different model rolls it too, since the route is part
 * of the digest.
 *
 * A chosen row that a later inventory refresh no longer reports as executable
 * is dropped back to the house route rather than sent anyway: the request must
 * never name a route the server has stopped vouching for. The only thing the
 * user sees of that is the picker's trigger returning to "Default" — no surface
 * announces it — and today it can only happen if a surface calls `refresh()`,
 * which none yet does; the guard is here so that adding one is safe.
 */

/** The server's own bar for an owner-executable route, mirrored client-side so
 *  a row that cannot be honoured is never offered. Matches the filter
 *  StartResearch applies to the same inventory. */
export const isExecutableUserModel = (model: UserModelRow): boolean =>
  model.enabled &&
  model.key_present &&
  model.registered &&
  model.route_eligible &&
  model.pricing_status === "known" &&
  model.hard_ceiling_eligible &&
  model.execution_status === "executable";

/** The two fields an owner-selected launch adds to a start request, or nothing
 *  at all when the house route is in force. */
export type OwnerLaunchFields =
  | { model_choice: UserModelChoice; operation_id: string }
  | Record<string, never>;

export interface OwnerModelChoiceState {
  /** Executable rows only — what the picker renders. */
  models: UserModelRow[];
  /** Honest inventory state; "error" means we could not read it, not "none". */
  state: "loading" | "ready" | "error";
  /** The chosen row, or null while the house route is in force. */
  selected: UserModelRow | null;
  /** `ModelUsagePicker`'s `value`: the row id, or "" for the house route. */
  selectedRowId: string;
  /** `ModelUsagePicker`'s `valueModelId`: the chosen variant under that row
   *  (one of its `model_ids`), or null for the row's primary. */
  selectedModelId: string | null;
  /** What the picker's trigger should read. */
  triggerLabel: string;
  /** `ModelUsagePicker`'s `onChange`; "" selects the house route. The
   *  optional second argument names a variant under the row (SPR-03 Task 2:
   *  one key, many variants); omitted means the row's primary. */
  select: (rowId: string, modelId?: string) => void;
  /** Spread into the start request. Both fields, or neither.
   *  `launchKey` is the request content this launch carries (the question, the
   *  piece title, the subject name): same key → same operation id, so a resend
   *  of the identical request replays instead of starting a second one. */
  launchFields: (launchKey: string) => OwnerLaunchFields;
  /** Re-read the inventory (a key added in Settings mid-session). */
  refresh: () => Promise<void>;
}

/**
 * @param operationPrefix short, surface-naming prefix for the minted
 *   idempotency id (e.g. "chat", "connect"), so a launch that has to be
 *   reconciled later is traceable to the surface that started it.
 */
export function useOwnerModelChoice(
  operationPrefix: string,
): OwnerModelChoiceState {
  const [models, setModels] = useState<UserModelRow[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [selectedRowId, setSelectedRowId] = useState("");
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  // The current launch identity: which content it was minted for, and the id
  // itself. A ref, not state — it is read and rolled inside submit, and no
  // render depends on it.
  const launchRef = useRef<{ key: string; id: string } | null>(null);

  const refresh = useCallback(async () => {
    setState("loading");
    try {
      const inventory = await fetchUserModels();
      setModels(inventory.models.filter(isExecutableUserModel));
      setState("ready");
    } catch {
      setModels([]);
      setState("error");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selected = useMemo(
    () => models.find((model) => model.id === selectedRowId) ?? null,
    [models, selectedRowId],
  );

  useEffect(() => {
    if (state === "ready" && selectedRowId && !selected) {
      setSelectedRowId("");
      setSelectedModelId(null);
      launchRef.current = null;
    }
  }, [state, selectedRowId, selected]);

  // The variant actually in force: the chosen one when the row still lists
  // it, else the row's primary. A variant the inventory no longer vouches
  // for is never sent, mirroring the row-level guard above.
  const effectiveModelId = selected
    ? selectedModelId && userModelVariants(selected).includes(selectedModelId)
      ? selectedModelId
      : selected.model_id
    : null;

  const select = useCallback((rowId: string, modelId?: string) => {
    setSelectedRowId(rowId);
    setSelectedModelId(rowId ? (modelId ?? null) : null);
    // The route is part of the launch digest, so a new choice is a new launch
    // and the next attempt must carry a new id rather than replay the last.
    launchRef.current = null;
  }, []);

  const launchFields = useCallback(
    (launchKey: string): OwnerLaunchFields => {
      if (!selected || !effectiveModelId) return {};
      if (!launchRef.current || launchRef.current.key !== launchKey) {
        launchRef.current = {
          key: launchKey,
          id: `${operationPrefix}-${crypto.randomUUID()}`,
        };
      }
      return {
        model_choice: {
          authority: "user_model",
          provider_id: selected.id,
          model_id: effectiveModelId,
        },
        operation_id: launchRef.current.id,
      };
    },
    [selected, effectiveModelId, operationPrefix],
  );

  const triggerLabel = selected
    ? effectiveModelId && effectiveModelId !== selected.model_id
      ? `${selected.display_name || selected.model_id} · ${effectiveModelId}`
      : selected.display_name || selected.model_id
    : "Default";

  return {
    models,
    state,
    selected,
    selectedRowId,
    selectedModelId: effectiveModelId,
    triggerLabel,
    select,
    launchFields,
    refresh,
  };
}
