/**
 * Product path: reading highlight/page → engagement session → floating
 * deep_research_session window (residual cc).
 *
 * Composes shipped `openEngagementSession` (API) + `openDeepResearchFromHighlight`
 * (window host). Does not reimplement spawn/session substrate.
 */

import { openEngagementSession } from "../../api/engagement";
import { openDeepResearchFromHighlight } from "../../workspace/deepResearchWindow";
import type { WindowMode } from "../../workspace/windowsStore";

export type LaunchFloatingDeepResearchInput = {
  asset_id: string;
  selection_text: string;
  region_id?: string | null;
  page?: number | null;
  goal_hint?: string | null;
  model_id?: string | null;
  view_mode?: WindowMode;
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
};

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
  const session = await openEngagementSession({
    asset_id: assetId,
    selection_text: selection,
    region_id: input.region_id,
    page: input.page,
    goal_hint: input.goal_hint,
    model_id: input.model_id,
    view_mode: mode === "full" ? "full" : "floating",
  });

  if (session.view_format !== "html") {
    throw new Error("session view_format must be html");
  }

  const windowId = openDeepResearchFromHighlight({
    asset_id: session.parent_asset_id || assetId,
    selection_text: session.selection_text || selection,
    session_id: session.session_id,
    spawn_id: session.spawn_id,
    investigation_id: session.investigation_id,
    region_id: input.region_id ?? undefined,
    model_id: session.model_id ?? input.model_id ?? undefined,
    status: session.status,
    goal: session.goal,
    mode: mode === "full" ? "full" : "floating",
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
  };
}
