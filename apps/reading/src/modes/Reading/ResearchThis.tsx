import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../../components/lemon";
import { spinResearch } from "../../api/books";
import { CollectiveResearchPanel } from "../../components/engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { TwinNotesPanel } from "../../components/engagement/TwinNotesPanel";
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../../components/engagement/PublicationAttachPanel";
import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import { track } from "../../lib/analytics";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../ResearchWorkstation/publicationRefs";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import type { WindowMode } from "../../workspace/windowsStore";
import { useWindows } from "../../workspace/windowsStore";
import { launchFloatingDeepResearch } from "./launchFloatingDeepResearch";
import {
  composeDriverPromptText,
  countPublicationRefs,
} from "../../lib/driverPromptText";

/**
 * ResearchThis (Read SPR-08 + residual cc/cu/cx/cy/de) — spin deep research from
 * the current passage.
 *
 * Residual (cc): primary path opens a **floating** deep_research_session
 * window via engagement sessions/open + openDeepResearchFromHighlight.
 * Residual (cu): optional arxiv/substack/URL refs hydrate + attach on open.
 * Residual (ahc): knowledge-dense pub quick-call presets on highlight DR path
 * (parity launch/chase/attach/hosted/marketplace matrix).
 * Residual (uk): pub-refs dual-gate L1/L2 hydrate readiness deep-links (parity uj).
 * Residual (cx): budget projection before fire (parity with StartResearch).
 * Residual (cy): decision-tree model_id resolved inside launchFloatingDeepResearch
 * (shared chokepoint with float-menu / HighlightToolbar).
 * Residual (et): full working-region deep_research_session window (view_mode
 * full) — distinct from legacy full-page ResearchWorkstation handoff.
 * Residual (fc): CollectiveResearchPanel when open DR spawns exist so the
 * main reading surface multi-select merges into this document (parity eu).
 * Residual (jg): Settings depth-tier prefill for budget projection (parity jc–jf).
 * Residual (ll): DecisionTreeDriverBadge researchTier before launch.
 * Residual (pi): DecisionTreeDriverBadge promptText = selection + pub refs
 * Residual (qr): budget panel uses same composeDriverPromptText (badge ≡ budget).
 * Residual (ahi): budget foresight pub-ref count (parity StartResearch ahg · chat ahh).
 * Residual (aie): operator-visible pub-ref foresight chrome (parity aic/aid).
 * for cost-vs-remaining projection (parity MO pg / Write ph).
 * Residual (agq): TwinNotes recursive note-taker for this book asset while
 * spinning DR (parity TalkToBook agm · MetaReading agn · reading ≡ research).
 * Full-page workstation handoff remains an explicit tertiary action.
 *
 * Gate-safe: passageText for gated books is still constrained server-side;
 * floating path uses the same asset_id + selection identity.
 */

export interface ResearchThisProps {
  documentId: string;
  pageIndex: number;
  /** The reader's selected text, if any. Ignored server-side for gated
   * books — passed only as a convenience for servable ones. */
  passageText?: string;
}

export default function ResearchThis({
  documentId,
  pageIndex,
  passageText,
}: ResearchThisProps) {
  const navigate = useNavigate();
  // Residual (fc/ob/oc): open + recent DR session spawns for collective multi-select.
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWindowId, setLastWindowId] = useState<string | null>(null);
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  /** Residual (jg): Settings depth-tier prefill for reading DR budget. */
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");

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

  const selection =
    (passageText || "").trim() ||
    `Page ${pageIndex + 1} of document ${documentId}`;

  const onProjectionChange = useCallback(
    (p: ResearchLaunchBudgetProjection) => {
      setBudgetWarn(p.wouldExceedBudget === true);
    },
    [],
  );

  const spinDeepResearchWindow = async (viewMode: WindowMode = "floating") => {
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
      const refs = parsePublicationRefs(pubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} pub asset(s)` +
            (hydrated.failed.length ? ` · ${hydrated.failed.length} failed` : "") +
            " · HTML-first",
        );
      }
      // Residual (cy): model_id resolved inside launchFloatingDeepResearch
      // (decision-tree driver when installed; never invented).
      // Residual (et): view_mode floating | full for window host (not /inv).
      const out = await launchFloatingDeepResearch({
        asset_id: documentId,
        selection_text: selection,
        page: pageIndex,
        goal_hint: "Deep-research the highlighted passage from reading",
        view_mode: viewMode,
        references: refs.length ? refs : undefined,
        // Residual (ji): pass Settings/picker tier onto reserved spawn.
        research_tier: researchTier,
      });
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
        mode: viewMode === "full" ? "full_window" : "floating_window",
        session_id: out.session_id,
        publication_ref_count: refs.length,
        model_id: out.model_id,
        research_tier: out.research_tier,
      });
      setLastWindowId(out.window_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const spinFullWorkstation = async () => {
    setBusy(true);
    setError(null);
    try {
      // Residual (jm): pass Settings/picker tier onto legacy full workstation spin.
      const res = await spinResearch(documentId, pageIndex, passageText, {
        researchTier,
      });
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
        mode: "full_workstation",
        research_tier: researchTier,
      });
      navigate(`/inv/${encodeURIComponent(res.investigation_id)}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2" data-testid="research-this">
      <div
        className="space-y-1 max-w-md"
        data-testid="research-this-pub-refs"
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
          htmlFor="research-this-refs-input"
        >
          Ground with pubs (optional · arxiv / substack / URL)
        </label>
        {/* Residual (ahc): highlight DR quick-call (parity hosted aha · marketplace ahb). */}
        <div
          className="flex flex-wrap gap-1 items-center"
          data-testid="research-this-publication-quick-call"
          data-preset-count={String(KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length)}
          data-seamless-pub-quick-call="true"
          data-auto-hydrate="false"
          role="group"
          aria-label="Knowledge-dense publication quick-call presets"
        >
          <span className="text-[10px] font-mono opacity-70 mr-1">Quick-call:</span>
          {KNOWLEDGE_DENSE_PUBLICATION_PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              data-testid={`research-this-preset-${p.id}`}
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
          id="research-this-refs-input"
          data-testid="research-this-refs-input"
          value={pubRefs}
          onChange={(e) => setPubRefs(e.target.value)}
          disabled={busy}
          rows={2}
          placeholder={"arxiv:1706.03762\nhttps://…"}
          className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
        />
        {/* Residual (uk): L1/L2 hydrate prep deep-links (parity hosted uj). */}
        <p className="text-[10px] font-mono space-x-2 opacity-80">
          <a
            href="/settings#hydrate-live-status"
            data-testid="research-this-hydrate-settings-link"
            className="underline hover:opacity-100"
            title="Settings publication hydrate readiness (arxiv/substack injectors · offline default)"
          >
            Settings · hydrate readiness
          </a>
          {/* Residual (xd): L1 arxiv checklist section deep-link (parity pubs xc). */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
            data-testid="research-this-hydrate-dual-gate-link"
            className="underline hover:opacity-100"
            title="Dual-gate L1 arxiv hydrate checklist (prep only · offline default)"
          >
            Dual-gate L1 arxiv checklist
          </a>
          {/* Residual (aao): L2 Substack section (parity aal–aan · reading DR). */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
            data-testid="research-this-hydrate-dual-gate-l2-link"
            className="underline hover:opacity-100"
            title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
          >
            Dual-gate L2 Substack checklist
          </a>
        </p>
        {pubRefStatus ? (
          <p
            className="text-[10px] font-mono text-aurora"
            data-testid="research-this-refs-status"
            role="status"
          >
            {pubRefStatus}
          </p>
        ) : null}
      </div>
      {/* Residual (cx/jg/ahi): daily budget + prompt projection · pub-ref foresight. */}
      <div
        className="max-w-md"
        data-testid="research-this-budget-mount"
        data-view-format="html"
        data-research-tier={researchTier}
        data-depth-prefill={depthPrefill}
        data-pub-ref-count={String(countPublicationRefs(pubRefs))}
        data-has-pub-refs={String(countPublicationRefs(pubRefs) > 0)}
        data-prompt-chars={String(
          composeDriverPromptText(selection, pubRefs).length,
        )}
      >
        {/* Residual (aie): operator-visible pub-ref foresight chrome (parity aic). */}
        {countPublicationRefs(pubRefs) > 0 ? (
          <p
            className="text-[10px] font-mono opacity-80 mb-1"
            data-testid="research-this-pub-ref-foresight-chrome"
            data-pub-ref-count={String(countPublicationRefs(pubRefs))}
            role="status"
          >
            Knowledge-dense pubs in projection:{" "}
            <strong>{countPublicationRefs(pubRefs)}</strong> ref
            {countPublicationRefs(pubRefs) === 1 ? "" : "s"} · chars=
            {composeDriverPromptText(selection, pubRefs).length} · soft budget
            below
          </p>
        ) : null}
        <p
          className="text-[11px] font-mono opacity-80"
          data-testid="research-this-depth-prefill"
          role="status"
        >
          Depth prefill: {depthPrefill}
          {depthPrefill === "installed"
            ? ` → ${researchTier}`
            : depthPrefill === "none"
              ? " (default deep)"
              : ""}
        </p>
        {/* Residual (ll): model driver + budget + depth before fire. */}
        <div
          data-testid="research-this-driver-badge-mount"
          data-view-format="html"
          data-research-tier={researchTier}
        >
          <DecisionTreeDriverBadge
            researchTier={researchTier}
            /* Residual (pi): selection + pub refs cost foresight. */
            promptText={composeDriverPromptText(selection, pubRefs)}
          />
        </div>
        <ResearchLaunchBudgetPanel
          promptText={composeDriverPromptText(selection, pubRefs)}
          researchTier={researchTier}
          allowTierPick
          onResearchTierChange={setResearchTier}
          onProjectionChange={onProjectionChange}
        />
        {budgetWarn ? (
          <label
            className="flex items-center gap-2 text-[11px] font-mono text-emperor"
            data-testid="research-this-over-budget-warn"
          >
            <input
              type="checkbox"
              data-testid="research-this-force-over-budget"
              checked={forceOverBudget}
              onChange={(e) => setForceOverBudget(e.target.checked)}
              disabled={busy}
            />
            Force open despite budget projection
          </label>
        ) : null}
      </div>
      <div className="inline-flex flex-wrap items-center gap-2">
        <LemonButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy || (budgetWarn && !forceOverBudget)}
          onClick={() => void spinDeepResearchWindow("floating")}
          title="Open deep research in a floating window over the scene"
          data-testid="research-this-floating"
        >
          {busy ? "Opening…" : "Deep research (window)"}
        </LemonButton>
        <LemonButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy || (budgetWarn && !forceOverBudget)}
          onClick={() => void spinDeepResearchWindow("full")}
          title="Open deep research expanded to full working region"
          data-testid="research-this-deep-full"
        >
          {busy ? "Opening…" : "Deep research (full)"}
        </LemonButton>
        <LemonButton
          type="button"
          variant="tertiary"
          size="sm"
          disabled={busy}
          onClick={() => void spinFullWorkstation()}
          title="Spin full Research workstation (legacy handoff)"
          data-testid="research-this-full"
        >
          {busy ? "Spinning…" : "Research this page"}
        </LemonButton>
        {lastWindowId ? (
          <span
            className="text-[11px] font-mono text-aurora"
            data-testid="research-this-window-id"
            role="status"
          >
            Window {lastWindowId}
          </span>
        ) : null}
        {error && (
          <span
            className="text-[11px] font-mono text-emperor"
            role="alert"
            data-testid="research-this-error"
          >
            {error === "book_not_found" ? "Book not found." : error}
          </span>
        )}
      </div>
      {/* Residual (agq): recursive note-taker twin for this book while launching DR. */}
      {documentId.trim() ? (
        <section
          className="mt-2 max-w-md space-y-1 border-t border-ink/10 pt-2 dark:border-bright/10"
          data-testid="research-this-twins-mount"
          data-view-format="html"
          data-document-id={documentId.trim()}
          data-seamless-research-this-twins="true"
          data-research-tier={researchTier}
        >
          <TwinNotesPanel
            assetId={documentId.trim()}
            autoLoad
            autoSeedIfEmpty
            seedTitle={documentId.trim()}
            seedBodyText={selection.trim() || documentId.trim()}
            researchTier={researchTier}
          />
        </section>
      ) : null}
      {/* Residual (fc/ou): multi-select open + recent DR spawns → this book. */}
      {documentId.trim() && availableSpawnIds.length > 0 ? (
        <section
          className="mt-2 max-w-md space-y-1 border-t border-ink/10 pt-2 dark:border-bright/10"
          data-testid="research-this-collective-mount"
          data-view-format="html"
          data-available-spawn-count={String(availableSpawnIds.length)}
          data-recent-count={String(recentSpawnIds.length)}
        >
          <CollectiveResearchPanel
            availableSpawnIds={availableSpawnIds}
            parentAssetId={documentId.trim()}
            recentSpawnIds={recentSpawnIds}
            openSpawnIds={openSpawnIds}
            onRecentSpawnsCleared={() => setRecentTick((n) => n + 1)}
          />
        </section>
      ) : null}
    </div>
  );
}
