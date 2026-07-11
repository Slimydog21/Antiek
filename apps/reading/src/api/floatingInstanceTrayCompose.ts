/**
 * Floating deep-research instance tray compose (pure).
 *
 * Operator vision: multiple floating deep researches open at once; select
 * one or many for fullscreen, collective pack, cohesive unit prompt, draft
 * merge, or full merge — without live dispatch.
 *
 * pack_dispatched always false.
 * merge_executed always false.
 * live_dispatched always false.
 */

export type TrayMemberStatus =
  | "proposed"
  | "open"
  | "completed"
  | "closed";

export type TrayAction =
  | "none"
  | "fullscreen_one"
  | "collective_pack"
  | "cohesive_prompt"
  | "draft_merge_one"
  | "full_merge_one";

export interface TrayMember {
  instance_id: string;
  parent_asset_id: string;
  status: TrayMemberStatus;
  view_mode?: string;
  highlight?: string;
  /** Always false when supplied — pure tray rejects live_dispatched true. */
  live_dispatched?: false;
  merge_executed?: false;
}

export interface FloatingInstanceTrayInput {
  parent_asset_id: string;
  members: TrayMember[];
  /** Selected instance ids (subset of members). */
  selected_instance_ids: string[];
  /** Intended tray action for selection. */
  action: TrayAction;
  operator_ack: boolean;
}

export interface FloatingInstanceTrayCompose {
  parent_asset_id: string;
  member_count: number;
  selected_count: number;
  selected_instance_ids: string[];
  action: TrayAction;
  /**
   * True when selection + action gates pass (and operator_ack for merge/pack).
   * Still never dispatches or merges.
   */
  tray_ready: boolean;
  /** Always false — collective pack never dispatches. */
  pack_dispatched: false;
  /** Always false — merge never executes. */
  merge_executed: false;
  /** Always false — no provider dispatch. */
  live_dispatched: false;
  notes: string[];
  authority: "floating_instance_tray_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose multi-instance floating tray readiness for operator actions.
 * Never live-dispatches; never merges.
 */
export function composeFloatingInstanceTray(
  input: FloatingInstanceTrayInput,
): FloatingInstanceTrayCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (!Array.isArray(input.members) || input.members.length === 0) {
    throw new Error("members must be a non-empty array");
  }
  if (!Array.isArray(input.selected_instance_ids)) {
    throw new Error("selected_instance_ids must be an array");
  }
  const action = input.action;
  if (
    action !== "none" &&
    action !== "fullscreen_one" &&
    action !== "collective_pack" &&
    action !== "cohesive_prompt" &&
    action !== "draft_merge_one" &&
    action !== "full_merge_one"
  ) {
    throw new Error("action invalid");
  }

  const notes: string[] = [
    "pack_dispatched=false — tray is pure selection/intent only",
    "merge_executed=false — no parent merge from tray",
    "live_dispatched=false — no provider dispatch",
  ];

  const byId = new Map<string, TrayMember>();
  for (let i = 0; i < input.members.length; i++) {
    const m = input.members[i];
    if (!m || typeof m !== "object") {
      throw new Error(`members[${i}] must be an object`);
    }
    const id = requireNonEmpty(m.instance_id, `members[${i}].instance_id`);
    const p = requireNonEmpty(
      m.parent_asset_id,
      `members[${i}].parent_asset_id`,
    );
    if (p !== parent_asset_id) {
      throw new Error("all members must share parent_asset_id");
    }
    if (
      m.status !== "proposed" &&
      m.status !== "open" &&
      m.status !== "completed" &&
      m.status !== "closed"
    ) {
      throw new Error(`members[${i}].status invalid`);
    }
    if (m.live_dispatched !== undefined && m.live_dispatched !== false) {
      throw new Error(`members[${i}].live_dispatched must be false when set`);
    }
    if (m.merge_executed !== undefined && m.merge_executed !== false) {
      throw new Error(`members[${i}].merge_executed must be false when set`);
    }
    if (byId.has(id)) {
      throw new Error(`duplicate instance_id: ${id}`);
    }
    byId.set(id, m);
  }

  const selected_instance_ids: string[] = [];
  const seenSel = new Set<string>();
  for (let i = 0; i < input.selected_instance_ids.length; i++) {
    const id = requireNonEmpty(
      input.selected_instance_ids[i],
      `selected_instance_ids[${i}]`,
    );
    if (!byId.has(id)) {
      throw new Error(`selected_instance_ids[${i}] not in members`);
    }
    if (seenSel.has(id)) {
      throw new Error(`duplicate selected_instance_id: ${id}`);
    }
    seenSel.add(id);
    selected_instance_ids.push(id);
  }

  const member_count = byId.size;
  const selected_count = selected_instance_ids.length;
  notes.push(`member_count=${member_count} · selected_count=${selected_count}`);

  let tray_ready = false;
  if (action === "none") {
    tray_ready = false;
    notes.push("action=none — no tray action selected");
  } else if (
    action === "fullscreen_one" ||
    action === "draft_merge_one" ||
    action === "full_merge_one"
  ) {
    if (selected_count !== 1) {
      notes.push(`action=${action} requires exactly 1 selected instance`);
    } else {
      const m = byId.get(selected_instance_ids[0])!;
      if (m.status === "closed") {
        notes.push(`action=${action} blocked — instance closed`);
      } else if (action === "full_merge_one") {
        if (m.status !== "completed") {
          notes.push("full_merge_one requires completed instance");
        } else if (!input.operator_ack) {
          notes.push("full_merge_one requires operator_ack");
        } else {
          tray_ready = true;
          notes.push("tray_ready=true · full_merge_one intent only");
        }
      } else if (action === "draft_merge_one") {
        if (
          m.status !== "proposed" &&
          m.status !== "open" &&
          m.status !== "completed"
        ) {
          notes.push("draft_merge_one requires proposed|open|completed");
        } else {
          tray_ready = true;
          notes.push("tray_ready=true · draft_merge_one intent only");
        }
      } else {
        // fullscreen_one
        tray_ready = true;
        notes.push("tray_ready=true · fullscreen_one view intent");
      }
    }
  } else {
    // collective_pack | cohesive_prompt
    if (selected_count < 2) {
      notes.push(`action=${action} requires ≥2 selected instances`);
    } else {
      let ok = true;
      for (const id of selected_instance_ids) {
        const m = byId.get(id)!;
        if (m.status === "closed") {
          ok = false;
          notes.push(`selected ${id} is closed`);
          break;
        }
        if (
          action === "collective_pack" &&
          m.status !== "open" &&
          m.status !== "completed" &&
          m.status !== "proposed"
        ) {
          ok = false;
          notes.push(`collective_pack rejects status=${m.status} on ${id}`);
          break;
        }
      }
      if (ok && !input.operator_ack) {
        notes.push(`${action} requires operator_ack`);
      } else if (ok) {
        tray_ready = true;
        notes.push(
          `tray_ready=true · ${action} multi-select intent only (no dispatch)`,
        );
      }
    }
  }

  notes.push("pack_dispatched=false");
  notes.push("merge_executed=false");
  notes.push("live_dispatched=false");

  return {
    parent_asset_id,
    member_count,
    selected_count,
    selected_instance_ids,
    action,
    tray_ready,
    pack_dispatched: false,
    merge_executed: false,
    live_dispatched: false,
    notes,
    authority: "floating_instance_tray_compose_advisory",
  };
}

export function formatFloatingInstanceTraySummary(
  c: FloatingInstanceTrayCompose,
): string {
  return (
    `tray_ready=${c.tray_ready} · action=${c.action} · ` +
    `selected=${c.selected_count}/${c.member_count} · ` +
    `pack_dispatched=false · merge_executed=false`
  );
}
