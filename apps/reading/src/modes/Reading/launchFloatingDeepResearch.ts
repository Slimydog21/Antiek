/**
 * Product path: reading highlight/page → engagement session → floating
 * deep_research_session window (residual cc/cy).
 *
 * Composes shipped `openEngagementSession` (API) + `openDeepResearchFromHighlight`
 * (window host). Does not reimplement spawn/session substrate.
 *
 * Residual (cy): when callers omit model_id, resolve Settings decision-tree
 * driver (installed only). Float-menu, ResearchThis, HighlightToolbar share
 * one chokepoint — never invent a model when none is installed.
 */

import { openEngagementSession } from "../../api/engagement";
import { fetchDecisionTreeSelection } from "../../api/settings";
import { openDeepResearchFromHighlight } from "../../workspace/deepResearchWindow";
import type { WindowMode } from "../../workspace/windowsStore";

export type LaunchFloatingDeepResearchInput = {
  asset_id: string;
  selection_text: string;
  region_id?: string | null;
  page?: number | null;
  goal_hint?: string | null;
  /** Explicit model; when null/undefined/empty, resolve decision-tree driver. */
  model_id?: string | null;
  /** arxiv/substack/url handles for spawn attach (residual cm) */
  references?: string[];
  view_mode?: WindowMode;
  /**
   * Residual (ji): closed research tier for reserved spawn.
   * When omitted, server normalizes to deep.
   */
  research_tier?: "fast" | "deep" | "wrestle" | null;
};

export type LaunchFloatingDeepResearchResult = {
  session_id: string;
  spawn_id: string;
  investigation_id: string;
  parent_asset_id: string;
  window_id: string;
  view_format: "html";
  view_mode: string;
  status: string;
  /** Model used for open (explicit or decision-tree); null when none. */
  model_id: string | null;
  /** Research tier recorded on the session (default deep). */
  research_tier: "fast" | "deep" | "wrestle" | string;
  /**
   * Residual (nw): Antiek-bench usage from sessions/open when present
   * (twin_chase | floating_deep_research).
   */
  usage_event?: {
    task_class: string;
    outcome: string;
    prompt_hint?: string;
    source?: string;
    model_id?: string | null;
  } | null;
};

/**
 * Resolve decision-tree driver model_id when installed.
 * Non-fatal on fetch failure — returns null (session may still open).
 */
export async function resolveDecisionTreeModelId(): Promise<string | null> {
  try {
    const tree = await fetchDecisionTreeSelection();
    if (tree.installed && tree.model_id?.trim()) {
      return tree.model_id.trim();
    }
  } catch {
    return null;
  }
  return null;
}

export async function launchFloatingDeepResearch(
  input: LaunchFloatingDeepResearchInput,
): Promise<LaunchFloatingDeepResearchResult> {
  const selection = (input.selection_text || "").trim();
  if (!selection) {
    throw new Error("selection_text is required");
  }
  const assetId = (input.asset_id || "").trim();
  if (!assetId) {
    throw new Error("asset_id is required");
  }

  const mode = input.view_mode ?? "floating";
  const refs = (input.references || [])
    .map((r) => (r || "").trim())
    .filter(Boolean);

  // Residual (cy): explicit non-empty model_id wins; otherwise decision-tree.
  const explicit = (input.model_id || "").trim();
  const modelId = explicit
    ? explicit
    : await resolveDecisionTreeModelId();

  // Residual (ji): only send closed-set tiers; omit when unset (server → deep).
  const rawTier = (input.research_tier || "").trim().toLowerCase();
  const researchTier =
    rawTier === "fast" || rawTier === "deep" || rawTier === "wrestle"
      ? rawTier
      : undefined;

  const session = await openEngagementSession({
    asset_id: assetId,
    selection_text: selection,
    region_id: input.region_id,
    page: input.page,
    goal_hint: input.goal_hint,
    model_id: modelId,
    references: refs.length ? refs : undefined,
    view_mode: mode === "full" ? "full" : "floating",
    research_tier: researchTier,
  });

  if (session.view_format !== "html") {
    throw new Error("session view_format must be html");
  }

  const resolvedModel =
    (session.model_id || "").trim() || modelId || null;
  const resolvedTier = (() => {
    const fromSession = (session.research_tier || "").trim().toLowerCase();
    if (
      fromSession === "fast" ||
      fromSession === "deep" ||
      fromSession === "wrestle"
    ) {
      return fromSession;
    }
    return researchTier ?? "deep";
  })();

  const windowId = openDeepResearchFromHighlight({
    asset_id: session.parent_asset_id || assetId,
    selection_text: session.selection_text || selection,
    session_id: session.session_id,
    spawn_id: session.spawn_id,
    investigation_id: session.investigation_id,
    region_id: input.region_id ?? undefined,
    model_id: resolvedModel ?? undefined,
    status: session.status,
    goal: session.goal,
    mode: mode === "full" ? "full" : "floating",
    // Residual (jk): carry tier into session host chrome payload.
    research_tier: resolvedTier,
  });

  return {
    session_id: session.session_id,
    spawn_id: session.spawn_id,
    investigation_id: session.investigation_id,
    parent_asset_id: session.parent_asset_id || assetId,
    window_id: windowId,
    view_format: "html",
    view_mode: session.view_mode || mode,
    status: session.status,
    model_id: resolvedModel,
    research_tier: resolvedTier,
    // Residual (nw): pass through Antiek-bench usage for chase/DR audit.
    usage_event: session.usage_event ?? null,
  };
}
