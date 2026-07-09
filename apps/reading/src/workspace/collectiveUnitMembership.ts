/**
 * collectiveUnitMembership — session-scoped history of cohesive unit members.
 *
 * Residual (py / FUTURE-AGENT V2): after collective continue-as-unit (or merge /
 * written analysis), re-open the unit by restoring the prior multi-select
 * spawn set. Pure sessionStorage; never invents spawn ids; max 24 units.
 */

export const COLLECTIVE_UNIT_MEMBERSHIP_KEY =
  "antiek.collective.unit_membership.v1";
export const COLLECTIVE_UNIT_MEMBERSHIP_MAX = 24;

export type CollectiveUnitMembership = {
  collective_id: string;
  spawn_ids: string[];
  parent_asset_id?: string | null;
  /** Written-analysis / draft document_id when known. */
  document_id?: string | null;
  saved_at: number;
};

type StoreShape = {
  last_collective_id: string | null;
  by_id: Record<string, CollectiveUnitMembership>;
};

function emptyStore(): StoreShape {
  return { last_collective_id: null, by_id: {} };
}

function readStore(): StoreShape {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return emptyStore();
  }
  try {
    const raw = window.sessionStorage.getItem(COLLECTIVE_UNIT_MEMBERSHIP_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return emptyStore();
    const obj = parsed as Partial<StoreShape>;
    const by_id: Record<string, CollectiveUnitMembership> = {};
    if (obj.by_id && typeof obj.by_id === "object") {
      for (const [k, v] of Object.entries(obj.by_id)) {
        const id = String(k || "").trim();
        if (!id || !v || typeof v !== "object") continue;
        const spawn_ids = Array.isArray((v as CollectiveUnitMembership).spawn_ids)
          ? (v as CollectiveUnitMembership).spawn_ids
              .map((x) => String(x ?? "").trim())
              .filter(Boolean)
          : [];
        if (spawn_ids.length < 1) continue;
        by_id[id] = {
          collective_id: id,
          spawn_ids,
          parent_asset_id:
            (v as CollectiveUnitMembership).parent_asset_id ?? null,
          document_id: (v as CollectiveUnitMembership).document_id ?? null,
          saved_at:
            typeof (v as CollectiveUnitMembership).saved_at === "number"
              ? (v as CollectiveUnitMembership).saved_at
              : Date.now(),
        };
      }
    }
    const last = String(obj.last_collective_id ?? "").trim() || null;
    return {
      last_collective_id: last && by_id[last] ? last : null,
      by_id,
    };
  } catch {
    return emptyStore();
  }
}

function writeStore(store: StoreShape): void {
  if (typeof window === "undefined" || !window.sessionStorage) return;
  try {
    // Cap by recency: keep newest COLLECTIVE_UNIT_MEMBERSHIP_MAX units.
    const entries = Object.values(store.by_id).sort(
      (a, b) => (b.saved_at || 0) - (a.saved_at || 0),
    );
    const kept = entries.slice(0, COLLECTIVE_UNIT_MEMBERSHIP_MAX);
    const by_id: Record<string, CollectiveUnitMembership> = {};
    for (const m of kept) by_id[m.collective_id] = m;
    const last =
      store.last_collective_id && by_id[store.last_collective_id]
        ? store.last_collective_id
        : kept[0]?.collective_id ?? null;
    window.sessionStorage.setItem(
      COLLECTIVE_UNIT_MEMBERSHIP_KEY,
      JSON.stringify({ last_collective_id: last, by_id }),
    );
  } catch {
    /* quota / private mode — non-fatal */
  }
}

/**
 * Persist unit membership for a collective_id (overwrite). Empty ids ignored.
 * Returns the stored membership or null if nothing valid to store.
 */
export function storeCollectiveUnitMembership(input: {
  collective_id: string;
  spawn_ids: readonly string[];
  parent_asset_id?: string | null;
  document_id?: string | null;
}): CollectiveUnitMembership | null {
  const collective_id = String(input.collective_id || "").trim();
  if (!collective_id) return null;
  const spawn_ids = Array.from(
    new Set(
      (input.spawn_ids || [])
        .map((x) => String(x ?? "").trim())
        .filter(Boolean),
    ),
  );
  if (spawn_ids.length < 1) return null;
  const store = readStore();
  // Monotonic saved_at so same-ms batch writes still cap by recency (not unstable sort).
  const maxAt = Object.values(store.by_id).reduce(
    (m, x) => Math.max(m, x.saved_at || 0),
    0,
  );
  const membership: CollectiveUnitMembership = {
    collective_id,
    spawn_ids,
    parent_asset_id: input.parent_asset_id?.trim() || null,
    document_id: input.document_id?.trim() || null,
    saved_at: Math.max(Date.now(), maxAt + 1),
  };
  store.by_id[collective_id] = membership;
  store.last_collective_id = collective_id;
  writeStore(store);
  return membership;
}

/** Lookup membership by collective_id. */
export function getCollectiveUnitMembership(
  collectiveId: string,
): CollectiveUnitMembership | null {
  const id = String(collectiveId || "").trim();
  if (!id) return null;
  return readStore().by_id[id] ?? null;
}

/** Most recently stored unit (for one-click restore). */
export function getLastCollectiveUnitMembership(): CollectiveUnitMembership | null {
  const store = readStore();
  if (store.last_collective_id && store.by_id[store.last_collective_id]) {
    return store.by_id[store.last_collective_id];
  }
  const entries = Object.values(store.by_id).sort(
    (a, b) => (b.saved_at || 0) - (a.saved_at || 0),
  );
  return entries[0] ?? null;
}

/**
 * Pure helper — intersection of membership spawn_ids with available list,
 * preserving membership order (not available order).
 */
export function restoreCollectiveSelection(
  membership: CollectiveUnitMembership | null | undefined,
  availableSpawnIds: readonly string[],
): string[] {
  if (!membership?.spawn_ids?.length) return [];
  const avail = new Set(
    (availableSpawnIds || []).map((x) => String(x ?? "").trim()).filter(Boolean),
  );
  return membership.spawn_ids
    .map((x) => String(x ?? "").trim())
    .filter((id) => id && avail.has(id));
}

/** Test / dogfood reset. */
export function clearCollectiveUnitMembership(): void {
  if (typeof window === "undefined" || !window.sessionStorage) return;
  try {
    window.sessionStorage.removeItem(COLLECTIVE_UNIT_MEMBERSHIP_KEY);
  } catch {
    /* non-fatal */
  }
}
