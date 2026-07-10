/**
 * HostedHtmlDocumentHost — window-native page for marketplace / account
 * hosted books (residual bt). HTML-first only; PDF never required as view.
 *
 * Residual (bw): mounts TwinNotesPanel + ResearchContextPanel so reading
 * and research share the recursive note-taker / context flywheel on the
 * same document_id used as engagement asset_id after host seed (bv).
 * Residual (cv): ResearchContextPanel autoLoad.
 * Residual (da): DecisionTreeDriverBadge + budget projection + deep research
 * float launch from the hosted book (reading ≡ research).
 * Residual (pj): DecisionTreeDriverBadge promptText = selection + pub refs
 * Residual (qs): budget panel shares composeDriverPromptText (badge ≡ budget).
 * Residual (ahl): budget foresight pub-ref count on hosted book DR (parity ahi).
 * Residual (aif): operator-visible pub-ref foresight chrome (parity aic–aie).
 * Residual (qu): Open Write dual handoff html_draft + twin_seed (parity marketplace/MO).
 * (parity ResearchThis pi / Write ph / MO pg).
 * Residual (dg): soft-gate deep research when budget would exceed.
 * Residual (ec): remount ResearchContextPanel after twin promote.
 * Residual (en): highlight inside hosted HTML body → selection drives float
 * DR + budget projection (fallback: title+asset when no selection).
 * Residual (er): optional arxiv/substack/URL pub refs hydrate + attach on
 * float open (parity with ResearchThis cu) — knowledge-dense grounding from
 * marketplace/hosted books.
 * Residual (uj): pub-refs panel dual-gate L1/L2 hydrate readiness deep-links
 * (offline default · never silent live hydrate).
 * Residual (es): launch deep research as full window (view_mode full) as well
 * as floating — north-star “open in full screen” without leaving the hosted book.
 * Residual (eu): mount CollectiveResearchPanel when open deep_research_session
 * spawns exist so multi-select merge/analysis runs against this book as parent
 * (reading ≡ research collective unit).
 * Residual (ez): remount TwinNotesPanel on the same refresh key as research
 * context so collective merge / promote reload recursive note-taker twins.
 * Residual (gn): allowTierPick on ResearchLaunchBudgetPanel (flash|pro|wrestle).
 * Residual (jd): prefill researchTier from Settings depth-tier (parity marketplace jc).
 * Residual (sh): source=evidence_pack honesty + recursive note-taker seed title
 * when citation-trust evidence floats from ResearchContextPanel (sf/sg).
 * Residual (tq): source=context_search carries search_query + search_hit_count
 * honesty chrome (intelligent search over recursive note-taker substrate).
 * Residual (ts): source=collective_unit_prompt honesty strip (collective_id ·
 * spawn_count) for multi-select cohesive unit HTML windows.
 * Residual (tu): Open Write title + twin_seed source preserve collective_unit_prompt
 * (store/load allowlist; no collapse to twin_draft_selected).
 * Residual (aen): Open Write stamps document_id + seamless-host-write path
 * honesty (hosted HTML reading surface → Write note-taker; parity ael/aem).
 *
 * Props arrive via WindowsLayer: `<Renderer {...win.payload} />`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import { launchFloatingDeepResearch } from "../../modes/Reading/launchFloatingDeepResearch";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../../modes/ResearchWorkstation/publicationRefs";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import type { WindowMode } from "../../workspace/windowsStore";
import { useWindows } from "../../workspace/windowsStore";
import { CollectiveResearchPanel } from "../engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../engagement/DecisionTreeDriverBadge";
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../engagement/PublicationAttachPanel";
import { ResearchContextPanel } from "../engagement/ResearchContextPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../engagement/ResearchLaunchBudgetPanel";
import { TwinNotesPanel } from "../engagement/TwinNotesPanel";
import { useInWindow } from "./windowHostContext";
import {
  composeDriverPromptText,
  countPublicationRefs,
} from "../../lib/driverPromptText";
import {
  buildHostedHtmlWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";

export type HostedHtmlDocumentHostProps = {
  document_id?: string;
  title?: string;
  html?: string;
  view_format?: string;
  license_class?: string;
  owner_id?: string;
  source?: string;
  /** Residual (ahr): research-domain subjects for intelligent search default. */
  subjects?: string[] | null;
  /** Residual (tq): intelligent search query when source=context_search. */
  search_query?: string | null;
  /** Residual (tq): hit count when source=context_search. */
  search_hit_count?: number | null;
  /** Residual (ts): collective cohesive unit id when source=collective_unit_prompt. */
  collective_id?: string | null;
  /** Residual (ts): multi-spawn count when source=collective_unit_prompt. */
  spawn_count?: number | null;
  research_tier?: string | null;
  __windowId?: string;
};

/** Residual (en): highlight passage wins; else whole-document fallback. */
export function resolveHostedResearchSelection(opts: {
  title: string;
  assetId: string;
  fallbackDocId: string;
  highlightText?: string | null;
}): { selection_text: string; from_highlight: boolean } {
  const highlight = (opts.highlightText || "").trim();
  if (highlight) {
    return { selection_text: highlight, from_highlight: true };
  }
  const id = opts.assetId || opts.fallbackDocId;
  return {
    selection_text: `Deep-research hosted document: ${opts.title} (${id})`,
    from_highlight: false,
  };
}

export default function HostedHtmlDocumentHost(
  props: HostedHtmlDocumentHostProps,
) {
  useInWindow();

  const docId = props.document_id?.trim() || "(missing document_id)";
  const title = props.title?.trim() || "Hosted document";
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  const isHtml = viewFormat === "html";
  const html = props.html?.trim() || "";
  const assetId = props.document_id?.trim() || "";

  // Residual (eu/ob/oc): open + recent DR session spawns for collective multi-select.
  const windows = useWindows((s) => s.windows);
  const [recentTick, setRecentTick] = useState(0);
  const recentSpawnIds = useMemo(
    () => listRecentDeepResearchSpawnIds(),
    [windows, recentTick],
  );
  /** Residual (ue): currently open DR windows only (no recent-ring closed ids). */
  const openSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        windows,
      }),
    [windows],
  );
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        windows,
        recentSpawnIds,
      }),
    [windows, recentSpawnIds],
  );

  const [highlightText, setHighlightText] = useState("");
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWindowId, setLastWindowId] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  /** Residual (jd): Settings depth-tier prefill for hosted book DR. */
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");

  // Residual (jd): prefill depth from Settings (parity marketplace jc / Midnight Oil gt).
  useEffect(() => {
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setResearchTier(mapped);
          setDepthPrefill("installed");
        } else {
          setDepthPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Residual (en): selection identity for float DR + budget.
  const { selection_text: researchSelection, from_highlight: fromHighlight } =
    useMemo(
      () =>
        resolveHostedResearchSelection({
          title,
          assetId,
          fallbackDocId: docId,
          highlightText,
        }),
      [title, assetId, docId, highlightText],
    );

  const captureHighlight = useCallback(() => {
    if (typeof window === "undefined" || !window.getSelection) return;
    const text = (window.getSelection()?.toString() || "").trim();
    // Only replace when the user actually selected something; empty
    // mouseup (click) keeps the last highlight so budget/DR stay stable.
    if (text) {
      setHighlightText(text.slice(0, 8000));
    }
  }, []);

  const clearHighlight = useCallback(() => {
    setHighlightText("");
  }, []);

  const onProjectionChange = useCallback(
    (p: ResearchLaunchBudgetProjection) => {
      setBudgetWarn(p.wouldExceedBudget === true);
    },
    [],
  );
  // Residual (ej): same naming as DR host context refresh chokepoint.
  const onContextNeedsRefresh = useCallback(() => {
    setContextRefreshKey((k) => k + 1);
  }, []);

  const spinDeepResearch = async (viewMode: WindowMode = "floating") => {
    if (!assetId) {
      setError("document_id is required for deep research");
      return;
    }
    if (!isHtml) {
      setError("view_format must be html");
      return;
    }
    if (budgetWarn && !forceOverBudget) {
      setError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce scope.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setPubRefStatus(null);
    try {
      // Capture latest selection at fire time (mouseup may lag React state).
      let selection = researchSelection;
      let goal = fromHighlight
        ? `Deep-research the highlighted passage from hosted book «${title}»`
        : `Deep-research the hosted book/document «${title}»`;
      if (typeof window !== "undefined" && window.getSelection) {
        const live = (window.getSelection()?.toString() || "").trim();
        if (live) {
          selection = live.slice(0, 8000);
          goal = `Deep-research the highlighted passage from hosted book «${title}»`;
          setHighlightText(selection);
        }
      }
      // Residual (er): optional knowledge-dense publication refs (HTML-first hydrate).
      const refs = parsePublicationRefs(pubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} pub asset(s)` +
            (hydrated.failed.length
              ? ` · ${hydrated.failed.length} failed`
              : "") +
            " · HTML-first",
        );
      }
      const out = await launchFloatingDeepResearch({
        asset_id: assetId,
        selection_text: selection,
        goal_hint: goal,
        view_mode: viewMode,
        references: refs.length ? refs : undefined,
        research_tier: researchTier,
      });
      setLastWindowId(out.window_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const payloadSource = (props.source || "").trim();
  const isEvidencePack = payloadSource === "evidence_pack";
  // Residual (sj): intelligent search HTML windows join note-taker path.
  const isContextSearch = payloadSource === "context_search";
  // Residual (sk): hydrated arxiv/substack HTML windows join note-taker path.
  const isPublicationHydrate = payloadSource === "publication_hydrate";
  const isResearchContextPack = payloadSource === "research_context_pack";
  // Residual (so): progress + flywheel float hosts join note-taker seed titles.
  const isResearchProgress =
    payloadSource === "research_progress_complete" ||
    payloadSource === "research_progress_draft";
  const isSessionFlywheel = payloadSource === "session_flywheel_complete";
  // Residual (tr): cohesive multi-spawn unit prompt HTML window.
  const isCollectiveUnitPrompt = payloadSource === "collective_unit_prompt";
  // Residual (vg): twin draft floats from TwinNotesPanel multi-select / cross-asset.
  const isTwinCrossAssetMerge = payloadSource === "twin_cross_asset_merge";
  const isTwinDraftSelected = payloadSource === "twin_draft_selected";
  // Residual (vk): multi-select written analysis float (not doc merge).
  const isCollectiveWrittenAnalysis =
    payloadSource === "collective_written_analysis";
  // Residual (vp): spawn/collective document merge floats.
  const isSpawnMerge = payloadSource === "spawn_merge";
  const isCollectiveDocMerge = payloadSource === "collective_doc_merge";
  // Residual (vr): marketplace host + Midnight Oil deposit floats.
  // Residual (aai): library open + rehydrate windows are still account-hosted
  // marketplace books — Open Write must map to marketplace_host write-seed feed
  // (not collapse to hosted_html_document).
  const isMarketplaceHost =
    payloadSource === "marketplace_host" ||
    payloadSource === "marketplace_library" ||
    payloadSource === "marketplace_library_rehydrate";
  // Residual (aaj): filter-aware catalog HTML projection (not a hosted book).
  const isMarketplaceCatalog = payloadSource === "marketplace_catalog";
  const isMidnightOilDeposit = payloadSource === "midnight_oil_deposit";
  // Residual (tq): intelligent search query + hit count honesty.
  const searchQuery = String(props.search_query || "").trim();
  const searchHitCount =
    typeof props.search_hit_count === "number" &&
    Number.isFinite(props.search_hit_count)
      ? Math.max(0, Math.floor(props.search_hit_count))
      : null;
  const collectiveId = String(props.collective_id || "").trim();
  const spawnCount =
    typeof props.spawn_count === "number" && Number.isFinite(props.spawn_count)
      ? Math.max(0, Math.floor(props.spawn_count))
      : null;
  // Residual (aiw): multi-hop hop honesty from evidence HTML projection (air).
  const evidenceHtml = isEvidencePack ? String(html || "") : "";
  const evidenceChainComplete =
    isEvidencePack && /chain_complete\s*=\s*true/i.test(evidenceHtml);
  const evidenceHasHopStrip =
    isEvidencePack &&
    (/Citation chain hops/i.test(evidenceHtml) ||
      /evidence-insight-\d+/i.test(evidenceHtml) ||
      /evidence-source-\d+/i.test(evidenceHtml));
  const twinSeedTitle = isEvidencePack
    ? `Evidence pack (citation trust) · ${title}`
    : isContextSearch
      ? searchQuery
        ? `Context search · “${searchQuery}” · ${title}`
        : `Context search · ${title}`
      : isPublicationHydrate
        ? `Hydrated publication · ${title}`
        : isResearchContextPack
          ? `Research context pack · ${title}`
          : isResearchProgress
            ? `Research progress · ${title}`
            : isSessionFlywheel
              ? `Session flywheel · ${title}`
              : isCollectiveUnitPrompt
                ? `Collective cohesive unit · ${title}`
                : isTwinCrossAssetMerge
                  ? `Twin cross-asset merge · ${title}`
                  : isTwinDraftSelected
                    ? `Twin multi-select draft · ${title}`
                    : isCollectiveWrittenAnalysis
                      ? `Collective written analysis · ${title}`
                      : isSpawnMerge
                        ? `Spawn merge · ${title}`
                        : isCollectiveDocMerge
                          ? `Collective document merge · ${title}`
                          : isMarketplaceHost
                            ? `Marketplace host · ${title}`
                            : isMarketplaceCatalog
                              ? `Marketplace catalog · ${title}`
                              : isMidnightOilDeposit
                                ? `Midnight Oil deposit · ${title}`
                                : title;
  // Residual (aiz): collective unit float twin seed body path honesty (FUTURE twin gap #2).
  const twinSeedBodyBase = html
    ? html.replace(/<[^>]+>/g, " ").slice(0, 500)
    : twinSeedTitle;
  const twinSeedBody = isCollectiveUnitPrompt
    ? [
        twinSeedBodyBase,
        "",
        "Port path: Collective cohesive unit float (multi-spawn merge · offline merge unit · L6 live multi-agent deferred · never invent server document_id).",
        collectiveId ? `collective_id=${collectiveId}` : "",
        spawnCount != null ? `spawn_count=${spawnCount}` : "",
        "source=collective_unit_prompt · HTML-first · twin auto-seed if empty.",
      ]
        .filter(Boolean)
        .join("\n")
        .slice(0, 900)
    : twinSeedBodyBase;

  return (
    <div
      className="flex h-full flex-col gap-3 bg-transparent p-6"
      data-testid="hosted-html-document-host"
      data-view-format={viewFormat}
      data-document-id={props.document_id ?? ""}
      data-source={payloadSource}
      data-evidence-pack={String(isEvidencePack)}
      data-evidence-chain-complete={
        isEvidencePack ? String(evidenceChainComplete) : ""
      }
      data-evidence-has-hop-strip={
        isEvidencePack ? String(evidenceHasHopStrip) : ""
      }
      data-context-search={String(isContextSearch)}
      data-search-query={isContextSearch ? searchQuery : ""}
      data-search-hit-count={
        isContextSearch && searchHitCount != null
          ? String(searchHitCount)
          : ""
      }
      data-collective-unit-prompt={String(isCollectiveUnitPrompt)}
      data-collective-id={isCollectiveUnitPrompt ? collectiveId : ""}
      data-spawn-count={
        isCollectiveUnitPrompt && spawnCount != null ? String(spawnCount) : ""
      }
      data-research-progress={String(isResearchProgress)}
      data-session-flywheel={String(isSessionFlywheel)}
    >
      <header className="space-y-1 border-b border-black/10 pb-3 dark:border-white/10">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="font-serif text-lg text-ink dark:text-parchment">
              {title}
            </h1>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              {docId}
              {props.license_class ? ` · ${props.license_class}` : ""}
              {" · "}
              content stance: {isHtml ? "HTML" : viewFormat} · not PDF
            </p>
            {/* Residual (tq): intelligent search honesty when floated from ResearchContext. */}
            {isContextSearch ? (
              <p
                className="text-[11px] font-mono opacity-80 mt-1"
                data-testid="hosted-html-context-search-honesty"
                data-search-query={searchQuery}
                data-search-hit-count={
                  searchHitCount != null ? String(searchHitCount) : ""
                }
                data-view-format="html"
                role="status"
              >
                Intelligent search
                {searchQuery ? (
                  <>
                    {" "}
                    · query=“{searchQuery}”
                  </>
                ) : null}
                {searchHitCount != null ? (
                  <> · hits={searchHitCount}</>
                ) : null}{" "}
                · recursive note-taker substrate · HTML · not PDF
              </p>
            ) : null}
            {/* Residual (aiw): evidence pack multi-hop hop honesty + scorecard nav. */}
            {isEvidencePack ? (
              <div
                className="text-[11px] font-mono opacity-80 mt-1 space-y-1"
                data-testid="hosted-html-evidence-pack-honesty"
                data-evidence-pack="true"
                data-chain-complete={String(evidenceChainComplete)}
                data-has-hop-strip={String(evidenceHasHopStrip)}
                data-view-format="html"
                role="status"
              >
                <p>
                  Evidence pack · citation trust ·{" "}
                  {evidenceChainComplete
                    ? "chain_complete=true (claims+sources)"
                    : "chain incomplete until claims+sources"}
                  {evidenceHasHopStrip
                    ? " · multi-hop hop strip present"
                    : " · hop strip absent"}{" "}
                  · HTML · not PDF · never invent sources
                </p>
                <p className="space-x-3">
                  <a
                    href="/settings#settings-competitive-dr-scorecard"
                    data-testid="hosted-html-evidence-scorecard-link"
                    className="underline opacity-90 hover:opacity-100"
                    title="Settings competitive deep-research scorecard (citation chain · multi-hop hops)"
                  >
                    Settings · competitive DR scorecard
                  </a>
                  <a
                    href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
                    data-testid="hosted-html-evidence-future-agent-link"
                    className="underline opacity-90 hover:opacity-100"
                    title="FUTURE-AGENT competitive deep-research quality brief"
                  >
                    FUTURE · competitive DR brief
                  </a>
                </p>
              </div>
            ) : null}
            {/* Residual (ts): multi-spawn cohesive unit honesty. */}
            {isCollectiveUnitPrompt ? (
              <div
                className="text-[11px] font-mono opacity-80 mt-1 space-y-1"
                data-testid="hosted-html-collective-unit-honesty"
                data-collective-id={collectiveId}
                data-spawn-count={
                  spawnCount != null ? String(spawnCount) : ""
                }
                data-twin-seed-path="collective_unit_prompt"
                data-auto-seed-if-empty="true"
                data-view-format="html"
                role="status"
              >
                <p>
                  Collective cohesive unit
                  {collectiveId ? (
                    <>
                      {" "}
                      · id={collectiveId}
                    </>
                  ) : null}
                  {spawnCount != null ? <> · spawns={spawnCount}</> : null} ·
                  multi-select merge · HTML · not PDF · no invented server doc ·
                  twin auto-seed if empty (recursive note-taker)
                </p>
                {/* Residual (aiz): twin seed + competitive honesty map from unit float. */}
                <p className="space-x-3">
                  <a
                    href="/settings#settings-competitive-dr-scorecard"
                    data-testid="hosted-html-collective-unit-scorecard-link"
                    className="underline opacity-90 hover:opacity-100"
                    title="Settings competitive DR scorecard (offline multi-agent merge shipped · L6 live deferred)"
                  >
                    Settings · competitive DR scorecard
                  </a>
                  <a
                    href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix.md"
                    data-testid="hosted-html-collective-unit-twin-matrix-link"
                    className="underline opacity-90 hover:opacity-100"
                    title="FUTURE-AGENT twin note-taker completeness matrix"
                  >
                    FUTURE · twin completeness matrix
                  </a>
                </p>
              </div>
            ) : null}
          </div>
          {/* Residual (da): driver readout on reading host (parity with DR). */}
          <div className="flex flex-col items-end gap-1">
            <DecisionTreeDriverBadge
              researchTier={researchTier}
              /* Residual (pj): selection + pub refs cost foresight. */
              promptText={composeDriverPromptText(researchSelection, pubRefs)}
            />
            {/* Residual (fl): handoff draft HTML into Write mode (import lands later). */}
            {assetId && isHtml ? (
              <a
                href={buildHostedHtmlWriteHref({
                  documentId: assetId,
                  title: props.title,
                  html,
                  // Residual (si): evidence_pack Write seeds record citation-trust source.
                  source: payloadSource || null,
                })}
                data-testid="hosted-html-open-write"
                data-view-format="html"
                data-has-twin-seed="1"
                // Residual (acn): body honesty on twin_seed (parity acf/ack/acl/acm).
                data-write-seed-has-body={String(
                  Boolean(isHtml && plainTextFromHtml(html || "").trim()),
                )}
                // Residual (aen): host document path honesty on Open Write link.
                data-document-id={assetId || ""}
                data-seamless-host-write={String(
                  Boolean(assetId && isHtml),
                )}
                data-write-seed-source={
                  isEvidencePack
                    ? "evidence_pack"
                    : isContextSearch
                      ? "context_search"
                      : isPublicationHydrate
                        ? "publication_hydrate"
                        : isResearchContextPack
                          ? "research_context_pack"
                          : isResearchProgress
                            ? payloadSource
                            : isSessionFlywheel
                              ? "session_flywheel_complete"
                              : isCollectiveUnitPrompt
                                ? "collective_unit_prompt"
                                : isTwinCrossAssetMerge
                                  ? "twin_cross_asset_merge"
                                  : isTwinDraftSelected
                                    ? "twin_draft_selected"
                                    : isCollectiveWrittenAnalysis
                                      ? "collective_written_analysis"
                                      : isSpawnMerge
                                        ? "spawn_merge"
                                        : isCollectiveDocMerge
                                          ? "collective_doc_merge"
                                          : isMarketplaceHost
                                            ? "marketplace_host"
                                            : isMarketplaceCatalog
                                              ? "marketplace_catalog"
                                              : isMidnightOilDeposit
                                                ? "midnight_oil_deposit"
                                                : "hosted_html_document"
                }
                className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
                title={
                  isEvidencePack
                    ? "Open Write with evidence pack HTML + twin_seed (citation trust · seeds note-taker)"
                    : isContextSearch
                      ? "Open Write with context search HTML + twin_seed (intelligent search · seeds note-taker)"
                      : isPublicationHydrate
                        ? "Open Write with hydrated publication HTML + twin_seed (seeds note-taker)"
                        : isResearchContextPack
                          ? "Open Write with research context pack HTML + twin_seed (seeds note-taker)"
                          : isCollectiveUnitPrompt
                            ? "Open Write with collective cohesive unit prompt HTML + twin_seed (multi-spawn unit · seeds note-taker)"
                            : isTwinCrossAssetMerge
                              ? "Open Write with twin cross-asset merge HTML + twin_seed (recursive note-taker · seeds note-taker)"
                              : isTwinDraftSelected
                                ? "Open Write with twin multi-select draft HTML + twin_seed (seeds note-taker)"
                                : isCollectiveWrittenAnalysis
                                  ? "Open Write with collective written analysis HTML + twin_seed (multi-spawn analysis · seeds note-taker)"
                                  : isSpawnMerge
                                    ? "Open Write with spawn merge HTML + twin_seed (seeds note-taker)"
                                    : isCollectiveDocMerge
                                      ? "Open Write with collective document merge HTML + twin_seed (seeds note-taker)"
                                      : isMarketplaceHost
                                        ? "Open Write with marketplace hosted book HTML + twin_seed (seeds note-taker)"
                                        : isMarketplaceCatalog
                                          ? "Open Write with marketplace catalog HTML + twin_seed (filter-aware listing · seeds note-taker)"
                                          : isMidnightOilDeposit
                                            ? "Open Write with Midnight Oil deposit HTML + twin_seed (seeds note-taker)"
                                            : isResearchProgress || isSessionFlywheel
                                              ? "Open Write with research HTML + twin_seed (seeds note-taker)"
                                              : "Open Write with hosted HTML + twin_seed (seeds note-taker when empty)"
                }
              >
                Open Write (HTML draft handoff)
              </a>
            ) : null}
          </div>
        </div>
      </header>

      {!isHtml ? (
        <p
          className="text-sm font-mono text-emperor"
          data-testid="hosted-html-reject-pdf"
        >
          view_format must be html — PDF is not a valid reading surface.
        </p>
      ) : html ? (
        <div
          className="prose min-h-0 flex-1 overflow-auto text-sm text-ink dark:text-parchment"
          data-testid="hosted-html-body"
          // Residual (en): capture highlight for float deep research.
          onMouseUp={captureHighlight}
          onKeyUp={captureHighlight}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <p
          className="text-sm font-mono text-ink-mute"
          data-testid="hosted-html-empty"
        >
          No HTML body yet — host the book into your account first.
        </p>
      )}

      {/* Residual (da/en): budget + float deep research from hosted book. */}
      {assetId && isHtml ? (
        <section
          className="mt-2 space-y-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-research-launch"
          data-view-format="html"
          data-from-highlight={fromHighlight ? "true" : "false"}
        >
          <div
            className="rounded border border-ink/10 p-2 text-[11px] font-mono dark:border-bright/10"
            data-testid="hosted-html-selection-preview"
            data-from-highlight={fromHighlight ? "true" : "false"}
          >
            <p className="text-shadow-1 dark:text-moonlight">
              {fromHighlight
                ? "Deep research will use your highlight:"
                : "No highlight — deep research uses whole document identity:"}
            </p>
            <p
              className="mt-1 max-h-16 overflow-auto text-ink dark:text-parchment"
              data-testid="hosted-html-selection-text"
            >
              {researchSelection.slice(0, 400)}
              {researchSelection.length > 400 ? "…" : ""}
            </p>
            {fromHighlight ? (
              <button
                type="button"
                className="mt-1 underline"
                data-testid="hosted-html-clear-highlight"
                onClick={clearHighlight}
                disabled={busy}
              >
                Clear highlight (use whole document)
              </button>
            ) : (
              <p className="mt-1 text-ink-mute dark:text-moonlight">
                Select text in the book above, then open deep research.
              </p>
            )}
          </div>
          {/* Residual (er/uj/aha): ground float DR with arxiv/substack/URL refs. */}
          <div
            className="space-y-1"
            data-testid="hosted-html-pub-refs"
            data-view-format="html"
            data-offline-default="true"
            data-l1-l2-hydrate-prep="true"
            data-seamless-pub-quick-call="true"
            data-knowledge-dense-presets={String(
              KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
            )}
          >
            <label
              className="text-[10px] font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight"
              htmlFor="hosted-html-refs-input"
            >
              Ground with pubs (optional · arxiv / substack / URL)
            </label>
            {/* Residual (aha): hosted book DR quick-call (parity launch/chase/attach). */}
            <div
              className="flex flex-wrap gap-1 items-center"
              data-testid="hosted-html-publication-quick-call"
              data-preset-count={String(
                KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
              )}
              data-seamless-pub-quick-call="true"
              data-auto-hydrate="false"
              role="group"
              aria-label="Knowledge-dense publication quick-call presets"
            >
              <span className="text-[10px] font-mono opacity-70 mr-1">
                Quick-call:
              </span>
              {KNOWLEDGE_DENSE_PUBLICATION_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  data-testid={`hosted-html-preset-${p.id}`}
                  data-preset-id={p.id}
                  data-kind={p.kind}
                  data-reference={p.reference}
                  data-auto-hydrate="false"
                  disabled={busy}
                  onClick={() => {
                    const ref = p.reference.trim();
                    if (!ref) return;
                    setPubRefs((prev) => {
                      const existing = new Set(
                        prev
                          .split(/\r?\n/)
                          .map((l) => l.trim())
                          .filter(Boolean),
                      );
                      if (existing.has(ref)) return prev;
                      const base = prev.trim();
                      return base ? `${base}\n${ref}` : ref;
                    });
                  }}
                  className="text-[10px] font-mono border rounded px-1.5 py-0.5 opacity-80 hover:opacity-100 disabled:opacity-50 border-ink/20 dark:border-bright/20"
                  title={`Insert ${p.reference} (hydrates offline-honest on DR launch · never auto-live)`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <textarea
              id="hosted-html-refs-input"
              data-testid="hosted-html-refs-input"
              value={pubRefs}
              onChange={(e) => setPubRefs(e.target.value)}
              disabled={busy}
              rows={2}
              placeholder={"arxiv:1706.03762\nhttps://…"}
              className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
            />
            {/* Residual (uj): L1/L2 hydrate prep deep-links (never enable live). */}
            <p className="text-[10px] font-mono space-x-2 opacity-80">
              <a
                href="/settings#hydrate-live-status"
                data-testid="hosted-html-hydrate-settings-link"
                className="underline hover:opacity-100"
                title="Settings publication hydrate readiness (arxiv/substack injectors · offline default)"
              >
                Settings · hydrate readiness
              </a>
              {/* Residual (xd): L1 arxiv checklist section deep-link (parity pubs xc). */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
                data-testid="hosted-html-hydrate-dual-gate-link"
                className="underline hover:opacity-100"
                title="Dual-gate L1 arxiv hydrate checklist (prep only · offline default)"
              >
                Dual-gate L1 arxiv checklist
              </a>
              {/* Residual (aam): L2 Substack section (parity marketplace aal). */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
                data-testid="hosted-html-hydrate-dual-gate-l2-link"
                className="underline hover:opacity-100"
                title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
              >
                Dual-gate L2 Substack checklist
              </a>
            </p>
            {pubRefStatus ? (
              <p
                className="text-[10px] font-mono text-aurora"
                data-testid="hosted-html-refs-status"
                role="status"
              >
                {pubRefStatus}
              </p>
            ) : null}
          </div>
          {/* Residual (jd/ahl): Settings depth prefill + tier pick · pub-ref foresight. */}
          <div
            data-testid="hosted-html-dr-depth-mount"
            data-research-tier={researchTier}
            data-depth-prefill={depthPrefill}
            data-view-format="html"
            data-pub-ref-count={String(countPublicationRefs(pubRefs))}
            data-has-pub-refs={String(countPublicationRefs(pubRefs) > 0)}
            data-prompt-chars={String(
              composeDriverPromptText(researchSelection, pubRefs).length,
            )}
          >
            {/* Residual (aif): operator-visible pub-ref foresight chrome (parity aic–aie). */}
            {countPublicationRefs(pubRefs) > 0 ? (
              <p
                className="text-[10px] font-mono opacity-80 mb-1"
                data-testid="hosted-html-pub-ref-foresight-chrome"
                data-pub-ref-count={String(countPublicationRefs(pubRefs))}
                role="status"
              >
                Knowledge-dense pubs in projection:{" "}
                <strong>{countPublicationRefs(pubRefs)}</strong> ref
                {countPublicationRefs(pubRefs) === 1 ? "" : "s"} · chars=
                {composeDriverPromptText(researchSelection, pubRefs).length} ·
                soft budget below
              </p>
            ) : null}
            <p
              className="text-[10px] font-mono text-ink-mute dark:text-moonlight mb-1"
              data-testid="hosted-html-dr-depth-prefill"
              role="status"
            >
              Depth prefill: {depthPrefill}
              {depthPrefill === "installed"
                ? ` → ${researchTier}`
                : depthPrefill === "none"
                  ? " (default deep)"
                  : ""}
            </p>
            <ResearchLaunchBudgetPanel
              promptText={composeDriverPromptText(researchSelection, pubRefs)}
              researchTier={researchTier}
              allowTierPick
              onResearchTierChange={setResearchTier}
              onProjectionChange={onProjectionChange}
            />
          </div>
          {budgetWarn ? (
            <label
              className="flex items-center gap-2 text-[11px] font-mono text-emperor"
              data-testid="hosted-html-over-budget-warn"
            >
              <input
                type="checkbox"
                data-testid="hosted-html-force-over-budget"
                checked={forceOverBudget}
                onChange={(e) => setForceOverBudget(e.target.checked)}
                disabled={busy}
              />
              Force open despite budget projection
            </label>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded border border-ink/20 px-3 py-1.5 text-xs font-mono dark:border-bright/20"
              data-testid="hosted-html-deep-research"
              disabled={busy || (budgetWarn && !forceOverBudget)}
              onClick={() => void spinDeepResearch("floating")}
            >
              {busy
                ? "Opening…"
                : fromHighlight
                  ? "Deep research highlight (window)"
                  : "Deep research (window)"}
            </button>
            {/* Residual (es): full window over the working region. */}
            <button
              type="button"
              className="rounded border border-ink/20 px-3 py-1.5 text-xs font-mono dark:border-bright/20"
              data-testid="hosted-html-deep-research-full"
              disabled={busy || (budgetWarn && !forceOverBudget)}
              onClick={() => void spinDeepResearch("full")}
              title="Open deep research expanded to full working region"
            >
              {busy ? "Opening…" : "Deep research (full)"}
            </button>
            {lastWindowId ? (
              <span
                className="text-[11px] font-mono text-aurora"
                data-testid="hosted-html-research-window-id"
                role="status"
              >
                Window {lastWindowId}
              </span>
            ) : null}
            {error ? (
              <span
                className="text-[11px] font-mono text-emperor"
                role="alert"
                data-testid="hosted-html-research-error"
              >
                {error}
              </span>
            ) : null}
          </div>
        </section>
      ) : null}

      {assetId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-twins-mount"
          data-view-format="html"
          data-source={payloadSource}
          data-evidence-pack={String(isEvidencePack)}
          data-context-search={String(isContextSearch)}
          data-collective-unit-prompt={String(isCollectiveUnitPrompt)}
          data-auto-seed-if-empty="true"
        >
          {/* Residual (ez): remount twins with context refresh key. */}
          {/* Residual (sh): evidence_pack seed title for recursive note-taker. */}
          {/* Residual (aiz): collective_unit_prompt twin seed path honesty. */}
          <div
            data-testid="hosted-html-twins-refresh"
            data-refresh-key={String(contextRefreshKey)}
            data-collective-unit-prompt={String(isCollectiveUnitPrompt)}
          >
            <TwinNotesPanel
              key={`twins-${assetId}-${contextRefreshKey}`}
              assetId={assetId}
              spawnId={null}
              autoLoad
              autoSeedIfEmpty
              autoPromoteAfterLoad
              onPromoted={onContextNeedsRefresh}
              seedTitle={twinSeedTitle}
              seedBodyText={twinSeedBody}
              researchTier={researchTier}
            />
          </div>
        </section>
      ) : null}

      {assetId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-context-mount"
          data-view-format="html"
          // Residual (ajf): free STEM catalog subjects → twin intelligent search default.
          data-domain-subjects={(props.subjects || []).join(",") || ""}
          data-has-domain-subjects={String(
            Boolean((props.subjects || []).filter(Boolean).length),
          )}
        >
          <div
            data-testid="hosted-html-context-refresh"
            data-refresh-key={String(contextRefreshKey)}
            data-domain-subjects={(props.subjects || []).join(",") || ""}
          >
            <ResearchContextPanel
              key={`ctx-${assetId}-${contextRefreshKey}`}
              assetId={assetId}
              spawnId={null}
              autoLoad
              domainSubjects={props.subjects || null}
            />
          </div>
        </section>
      ) : null}

      {/* Residual (eu/ov): multi-select open + recent DR spawns → this book. */}
      {assetId && isHtml && availableSpawnIds.length > 0 ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-collective-mount"
          data-view-format="html"
          data-available-spawn-count={String(availableSpawnIds.length)}
          data-recent-count={String(recentSpawnIds.length)}
        >
          <CollectiveResearchPanel
            availableSpawnIds={availableSpawnIds}
            parentAssetId={assetId}
            recentSpawnIds={recentSpawnIds}
            openSpawnIds={openSpawnIds}
            onDocMerged={onContextNeedsRefresh}
            onRecentSpawnsCleared={() => setRecentTick((n) => n + 1)}
          />
        </section>
      ) : null}
    </div>
  );
}
