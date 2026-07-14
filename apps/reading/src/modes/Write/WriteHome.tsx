import { capabilityGuidanceLinks } from "../../workspace/capabilityGuidanceLinks";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  createDeliverable,
  createSection,
  getDeliverable,
  listDeliverables,
  updateSectionProse,
  type DeliverableDetailResponse,
  type DeliverableKind,
  type DeliverableSummary,
} from "../../lib/api";
import { seedTwinNotes } from "../../api/engagement";
import { fetchHostedDocumentHtml } from "../../api/marketplaceHost";
import { CollectiveResearchPanel } from "../../components/engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../../components/engagement/PublicationAttachPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { ResearchContextPanel } from "../../components/engagement/ResearchContextPanel";
import { TwinNotesPanel } from "../../components/engagement/TwinNotesPanel";
import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import GlassSurface from "../../shell/GlassSurface";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import { competitiveDrOfflineSurfaceCatalog } from "../../workspace/competitiveDrQuality";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import { sanitizeHostedHtml } from "../../lib/sanitizeHostedHtml";
import {
  formatTwinWriteSeedFreeform,
  loadTwinWriteSeed,
  type TwinWriteSeedPayload,
} from "../../workspace/twinWriteSeed";
import type { WindowMode } from "../../workspace/windowsStore";
import { useWindows } from "../../workspace/windowsStore";
import Canvas from "../DeepResearchWorkspace/Canvas/Canvas";
import { launchFloatingDeepResearch } from "../Reading/launchFloatingDeepResearch";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../ResearchWorkstation/publicationRefs";
import BlockRepository from "./BlockRepository";
import ConnectResearch from "./ConnectResearch";
import { ContextWindow } from "./ContextWindow/ContextWindow";
import { IdeaDump } from "./Brainstorm/IdeaDump";
import Outline from "./Outline";
import { ProjectTypeField } from "./ProjectType";
import { onTraceIntent } from "./Editor/traceIntent";
import {
  prepareHtmlDraftForWrite,
  type HtmlDraftImportPrepared,
} from "./htmlDraftImport";
import { handoffWriteBlockToRead, traceReaderPath, type RepositoryHit } from "./writeApi";
import { composeDriverPromptText } from "../../lib/driverPromptText";

/**
 * Write Home — the Write door (Product Depth SPR-07 M1).
 *
 * Replaces the legacy CreationStudio dead-end ("Select or create a deliverable
 * to begin.") as the surface the Write rail opens. It teaches the whole loop
 * in one screen: a piece on the left as a legible outline, your block
 * repository on the right as a search-first TAP-to-add picker, one obvious
 * "Generate draft" per section, the real editor where the draft lands, and a
 * brainstorm on-ramp for starting from a raw idea instead of an outline.
 *
 * The create-deliverable button itself is hotfixed on `fix/lived-bugs`; this
 * surface owns the loop BEHIND it — once a piece exists (or you start one
 * here), the blocks→outline→generate→edit flow lives here.
 *
 * Routing: `/write` lands here with no piece (start one or brainstorm);
 * `/write/:deliverableId` opens onto that piece's outline. No id is ever
 * shown — the piece is named by its title, blocks by their text + provenance.
 *
 * Residual (fl): `?html_draft=<document_id>` handoff from hosted HTML merge.
 * Residual (fm): load hosted HTML, refuse non-html, prefill title + seed
 * brainstorm plain text.
 * Residual (ft): on create piece with loaded HTML draft, create section(s)
 * and PATCH prose (HTML-first land into outline).
 * Residual (fu): multi-section import via h1–h3 split (outline_sections).
 * Residual (fv): nest h2/h3 under preceding higher-level section via
 * parent_section_id when createSection accepts it.
 * Residual (fx): prefer html_fragment for section prose (HTML-first land).
 * Residual (fz): offline twin seed on deliverable after HTML draft import
 * (recursive note-taker substrate for the new writing asset).
 * Residual (ga): TwinNotesPanel on open piece so writing assets share the
 * recursive note-taker UI with reading/research hosts.
 * Residual (gb): ResearchContextPanel on open piece + remount after twin
 * Residual (amq): Write piece ResearchContext inherits writeResearchTier prefill
 * (parity host-tier path amj–amp · reading ≡ research ≡ writing).
 * promote (reading≡write context flywheel).
 * Residual (gc): DecisionTreeDriverBadge on open piece (model + budget bar).
 * Residual (gd): re-import html_draft into an existing open piece (not only create).
 * Residual (ge): deep research launch + pub refs on open piece (reading≡write
 * parity with hosted HTML host: arxiv/substack grounding, float|full, budget soft-gate).
 * Residual (if): Settings deep-link beside Write piece driver badge.
 * Residual (gf/om): CollectiveResearchPanel on open piece when DR spawns exist
 * (includes recent_ring so twin-chase closed windows still multi-select).
 * (multi-select merge/analysis with writing asset as parent).
 * Residual (ph): DecisionTreeDriverBadge promptText = DR selection + pub refs
 * Residual (qs): budget panel shares composeDriverPromptText (badge ≡ budget).
 * for cost-vs-remaining projection (parity MO pg / FUTURE-AGENT V4).
 * Residual (pp): `?twin_seed=<sessionStorage key>` handoff from TwinNotes
 * multi-select draft — seeds brainstorm + freeform provenance (HTML-first).
 * Residual (pq): on create with twin_seed, offline-seed twin notes onto the new
 * writing asset so recursive note-taker substrate continues into Write.
 * Residual (pu): twin seed handoff banner echoes note_ids provenance (parity pt).
 * Residual (qx): freeform + banner include twin seed source
 * (deep_research_session / research_progress_complete / …) for audit.

 * Residual (gg): remount TwinNotesPanel on same refresh key as research
 * context (DR launch / collective merge / promote / re-import) — hosted ez parity.
 * Residual (gh): live selection drives Write DR budget projection + launch
 * (mouseup capture; clear returns to whole-piece fallback).
 * Residual (jh): Settings depth-tier prefill for Write piece DR budget
 * (parity jc–jg · reading≡research≡write).
 * Residual (anv): knowledge-dense pub quick-call on open-piece DR path
 * (parity Midnight Oil anu · ResearchThis ahc · reading≡research≡writing).
 * Residual (anx): L1/L2 dual-gate hydrate prep deep-links on write-piece pubs
 * (parity ResearchThis uk · MO pb · offline-honest never enable injectors).
 */
export default function WriteHome() {
  const { deliverableId } = useParams<{ deliverableId?: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Residual (fl/fm): HTML draft handoff from reading/research merge flywheel.
  const htmlDraftId = useMemo(
    () => (searchParams.get("html_draft") || "").trim(),
    [searchParams],
  );
  // Residual (pp): twin multi-select draft seed from TwinNotesPanel.
  const twinSeedKey = useMemo(
    () => (searchParams.get("twin_seed") || "").trim(),
    [searchParams],
  );
  // Residual (gf/om): open + recent DR session spawns for collective on Write.
  const windows = useWindows((s) => s.windows);
  const [recentTick, setRecentTick] = useState(0);
  const recentSpawnIds = useMemo(
    () => listRecentDeepResearchSpawnIds(),
    [windows, recentTick],
  );
  /** Residual (uf): currently open DR windows only (parity ue Select open). */
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

  const [detail, setDetail] = useState<DeliverableDetailResponse | null>(null);
  const [pieces, setPieces] = useState<DeliverableSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [onRamp, setOnRamp] = useState<"idea" | "context" | null>(null);
  // Residual (gb): remount research context after twin promote on Write piece.
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  // Residual (fm): prepared HTML draft for Write surface.
  const [htmlDraft, setHtmlDraft] = useState<HtmlDraftImportPrepared | null>(
    null,
  );
  const [htmlDraftError, setHtmlDraftError] = useState<string | null>(null);
  const [htmlDraftBusy, setHtmlDraftBusy] = useState(false);
  const [brainstormSeed, setBrainstormSeed] = useState<string | null>(null);
  // Residual (pp): twin seed handoff banner payload.
  const [twinSeed, setTwinSeed] = useState<TwinWriteSeedPayload | null>(null);
  const [reimportBusy, setReimportBusy] = useState(false);
  const [reimportStatus, setReimportStatus] = useState<string | null>(null);
  // Residual (ge): write-piece deep research launch (parity with hosted host).
  const [writePubRefs, setWritePubRefs] = useState("");
  const [writePubRefStatus, setWritePubRefStatus] = useState<string | null>(null);
  const [writeDrBusy, setWriteDrBusy] = useState(false);
  const [writeDrError, setWriteDrError] = useState<string | null>(null);
  const [writeDrWindowId, setWriteDrWindowId] = useState<string | null>(null);
  const [writeBudgetWarn, setWriteBudgetWarn] = useState(false);
  const [writeForceOverBudget, setWriteForceOverBudget] = useState(false);
  // Residual (gh): highlight selection for Write DR budget + launch.
  const [writeHighlightText, setWriteHighlightText] = useState("");
  /** Residual (jh): Settings depth-tier prefill for Write piece DR budget. */
  const [writeResearchTier, setWriteResearchTier] =
    useState<ResearchLaunchTier>("deep");
  const [writeDepthPrefill, setWriteDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");
  useEffect(() => {
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setWriteResearchTier(mapped);
          setWriteDepthPrefill("installed");
        } else {
          setWriteDepthPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setWriteDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const onContextNeedsRefresh = useCallback(() => {
    setContextRefreshKey((k) => k + 1);
  }, []);
  const onWriteDrProjectionChange = useCallback(
    (p: ResearchLaunchBudgetProjection) => {
      setWriteBudgetWarn(p.wouldExceedBudget === true);
    },
    [],
  );
  const captureWriteHighlight = useCallback(() => {
    if (typeof window === "undefined" || !window.getSelection) return;
    const text = (window.getSelection()?.toString() || "").trim();
    // Empty mouseup keeps last highlight so budget/DR stay stable.
    if (text) {
      setWriteHighlightText(text.slice(0, 8000));
    }
  }, []);
  const clearWriteHighlight = useCallback(() => {
    setWriteHighlightText("");
  }, []);
  /** Residual (gh): selection for budget panel + launch — highlight wins. */
  const writeResearchPromptText = useMemo(() => {
    const highlight = writeHighlightText.trim();
    if (highlight) return highlight;
    const title = detail?.title?.trim() || "writing piece";
    const id = detail?.deliverable_id || deliverableId || "";
    return `Deep-research writing piece: ${title} (${id})`;
  }, [writeHighlightText, detail?.title, detail?.deliverable_id, deliverableId]);
  // The "start a piece" action — must be declared before html_draft load effect.
  const [starting, setStarting] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  // Open-ended project type (M4): freeform text the AI interprets; presets seed.
  const [projectType, setProjectType] = useState<{
    freeform: string;
    kind: DeliverableKind;
  }>({ freeform: "", kind: "general_essay" });
  // The piece-view surface: the outline loop, or the imported research canvas
  // (M1 — the SPR-03 Canvas of the linked investigation's blocks).
  const [pieceView, setPieceView] = useState<"outline" | "canvas">("outline");

  // The active tap-to-add handler, registered by the Outline (binds the tap to
  // the active section). A ref so re-registers don't re-render the repository.
  const addHandler = useRef<(hit: RepositoryHit) => void>(() => {});
  const registerAddHandler = useCallback((h: (hit: RepositoryHit) => void) => {
    addHandler.current = h;
  }, []);

  const refresh = useCallback(async () => {
    if (!deliverableId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    try {
      setDetail(await getDeliverable(deliverableId));
    } catch {
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [deliverableId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (deliverableId) return; // only list pieces on the home (no piece) view
    listDeliverables()
      .then((r) => setPieces(r.deliverables))
      .catch(() => setPieces([]));
  }, [deliverableId]);

  // Residual (pp): load twin write seed from sessionStorage (home path).
  useEffect(() => {
    if (!twinSeedKey || deliverableId) {
      if (!twinSeedKey) setTwinSeed(null);
      return;
    }
    const loaded = loadTwinWriteSeed(twinSeedKey);
    setTwinSeed(loaded);
    if (!loaded) return;
    setBrainstormSeed(loaded.plain_text.slice(0, 8000));
    setOnRamp("idea");
    setNewTitle((prev) => (prev.trim() ? prev : loaded.title.slice(0, 200)));
    setProjectType((prev) =>
      prev.freeform.trim()
        ? prev
        : {
            ...prev,
            // Residual (qx): include source for DR/progress audit trail.
            freeform: formatTwinWriteSeedFreeform(loaded),
          },
    );
  }, [deliverableId, twinSeedKey]);

  // Residual (fm/gd): load hosted HTML draft on home OR open piece handoff.
  useEffect(() => {
    if (!htmlDraftId) {
      setHtmlDraft(null);
      setHtmlDraftError(null);
      setReimportStatus(null);
      return;
    }
    let cancelled = false;
    setHtmlDraftBusy(true);
    setHtmlDraftError(null);
    void fetchHostedDocumentHtml(htmlDraftId)
      .then((doc) => {
        if (cancelled) return;
        const prepared = prepareHtmlDraftForWrite({
          document_id: doc.document_id || htmlDraftId,
          view_format: doc.view_format,
          html: doc.html,
          title: doc.title,
        });
        setHtmlDraft(prepared);
        // Prefill only on create-home path (not re-import into open piece).
        if (!deliverableId) {
          setNewTitle((prev) => (prev.trim() ? prev : prepared.title_hint));
          // Residual (fp): stamp project-type freeform with HTML draft provenance.
          setProjectType((prev) =>
            prev.freeform.trim()
              ? prev
              : {
                  ...prev,
                  freeform: `html_draft:${prepared.document_id}`,
                },
          );
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setHtmlDraft(null);
        setHtmlDraftError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setHtmlDraftBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deliverableId, htmlDraftId]);

  // Trace-to-source (M4): when a citation chip in the editor is clicked it
  // emits a decoupled intent (Editor/traceIntent.ts). Commit the durable seam,
  // then route to the shared HTML reader only when current source authority
  // permits it; gated or unavailable sources never become a side door.
  useEffect(() => {
    return onTraceIntent((intent) => {
      if (!intent.outlineBlockId) {
        window.alert("This is your own note — it traces to your session, not an external source.");
        return;
      }
      void (async () => {
        try {
          const pieceId = detail?.deliverable_id ?? deliverableId;
          if (!pieceId) {
            window.alert("Open the piece that owns this citation before tracing it.");
            return;
          }
          const target = await handoffWriteBlockToRead(
            intent.outlineBlockId!,
            pieceId,
          );
          const readerPath = traceReaderPath(target, pieceId);
          if (readerPath) {
            navigate(readerPath);
          } else {
            // Honest fallback (§9.0): gated/unreachable source — say so, don't
            // open a dead page.
            window.alert(
              target.detail ??
                "That source isn't available to open here — it's gated or not reachable yet.",
            );
          }
        } catch {
          window.alert("Couldn't reach that source right now. Try again.");
        }
      })();
    });
  }, [deliverableId, detail?.deliverable_id, navigate]);

  // The "start a piece" action — the obvious way to begin (WX-01). SPR-09 M1:
  // it now runs title → project-type → connect-to-research, so a piece is
  // created WITH its backing investigation_root_id set (the link is set at
  // creation; M1 reads it back to verify it exists).

  /** Residual (ft/fu/fv/fx/gd): land htmlDraft sections into a deliverable. */
  const importHtmlDraftIntoDeliverable = useCallback(
    async (
      targetDeliverableId: string,
      opts?: { twinTitle?: string; seedTwins?: boolean },
    ): Promise<number> => {
      if (!htmlDraft) return 0;
      const sections =
        htmlDraft.outline_sections?.length > 0
          ? htmlDraft.outline_sections
          : htmlDraft.plain_text?.trim()
            ? [
                {
                  title: (htmlDraft.title_hint || "Imported HTML draft").slice(
                    0,
                    120,
                  ),
                  plain_text: htmlDraft.plain_text,
                  section_index: 0,
                  heading_level: 0,
                  html_fragment: htmlDraft.html.slice(0, 100_000),
                },
              ]
            : [];
      // Offset section_index when appending to an existing piece (gd).
      const indexOffset = opts?.seedTwins === false ? (detail?.sections?.length ?? 0) : 0;
      const lastIdByLevel: Record<number, string> = {};
      let imported = 0;
      for (const s of sections) {
        if (!s.plain_text?.trim()) continue;
        const level = s.heading_level ?? 0;
        let parent_section_id: string | undefined;
        if (level >= 2) {
          for (let p = level - 1; p >= 0; p--) {
            if (lastIdByLevel[p]) {
              parent_section_id = lastIdByLevel[p];
              break;
            }
          }
        }
        const sec = await createSection({
          deliverable_id: targetDeliverableId,
          section_index: s.section_index + indexOffset,
          title: (s.title || "Imported section").slice(0, 120),
          ...(parent_section_id ? { parent_section_id } : {}),
        });
        lastIdByLevel[level] = sec.section_id;
        for (const k of Object.keys(lastIdByLevel)) {
          const kl = Number(k);
          if (kl > level) delete lastIdByLevel[kl];
        }
        const prose =
          (s.html_fragment || "").trim() || s.plain_text.slice(0, 100_000);
        await updateSectionProse(sec.section_id, {
          prose_text: prose.slice(0, 100_000),
          promote_to_graph: false,
        });
        imported += 1;
      }
      if (opts?.seedTwins !== false) {
        try {
          await seedTwinNotes({
            asset_id: targetDeliverableId,
            title: opts?.twinTitle || htmlDraft.title_hint,
            body_text: htmlDraft.plain_text.slice(0, 2000),
            include_html: false,
            force_offline: true,
          });
        } catch {
          // Twin seed optional.
        }
      }
      return imported;
    },
    [htmlDraft, detail?.sections?.length],
  );

  async function createWithConnection(resolved: { investigationId: string; label: string }) {
    if (!newTitle.trim()) return;
    setStarting(true);
    try {
      const d = await createDeliverable({
        title: newTitle.trim(),
        // The freeform type resolves to the closest kind (ProjectType.resolveKind);
        // a novel type falls to general_essay — never gated, never crashes.
        deliverable_kind: projectType.kind,
        // M1: the piece↔research link, set at creation (deliverables.
        // investigation_root_id; reused, not a new column — see decision D-1).
        investigation_root_id: resolved.investigationId,
      });
      if (htmlDraft) {
        try {
          await importHtmlDraftIntoDeliverable(d.deliverable_id, {
            twinTitle: newTitle.trim() || htmlDraft.title_hint,
            seedTwins: true,
          });
        } catch {
          // Non-fatal: piece still opens; operator can paste from brainstorm seed.
        }
      }
      // Residual (pq): twin_seed path — reinforce recursive note-taker on new piece.
      if (twinSeed && twinSeed.plain_text.trim()) {
        try {
          await seedTwinNotes({
            asset_id: d.deliverable_id,
            title: newTitle.trim() || twinSeed.title,
            body_text: twinSeed.plain_text.slice(0, 2000),
            include_html: false,
            force_offline: true,
            // Residual (qy): feed Antiek-bench by_source for DR write seeds.
            usage_source: twinSeed.source,
            // Residual (adq): preserve Open Write body honesty (title-only → false).
            has_body: twinSeed.has_body,
          });
        } catch {
          // Non-fatal: piece still opens; operator has brainstorm seed.
        }
      }
      navigate(`/write/${d.deliverable_id}`);
    } finally {
      setStarting(false);
    }
  }

  /** Residual (gd): append html_draft sections into the open piece. */
  async function importIntoOpenPiece() {
    if (!detail?.deliverable_id || !htmlDraft) return;
    setReimportBusy(true);
    setReimportStatus(null);
    try {
      const n = await importHtmlDraftIntoDeliverable(detail.deliverable_id, {
        twinTitle: detail.title || htmlDraft.title_hint,
        seedTwins: false, // twins already exist on open piece
      });
      setReimportStatus(`Imported ${n} section(s) from HTML draft.`);
      await refresh();
      onContextNeedsRefresh();
    } catch (e) {
      setReimportStatus(
        e instanceof Error ? e.message : String(e),
      );
    } finally {
      setReimportBusy(false);
    }
  }

  /**
   * Residual (ge): launch deep research from open Write piece.
   * Highlight text wins; else title-based selection. Optional pub refs.
   */
  async function spinWriteDeepResearch(viewMode: WindowMode = "floating") {
    const assetId = detail?.deliverable_id;
    if (!assetId) {
      setWriteDrError("Open a writing piece before launching deep research.");
      return;
    }
    if (writeBudgetWarn && !writeForceOverBudget) {
      setWriteDrError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce scope.",
      );
      return;
    }
    setWriteDrBusy(true);
    setWriteDrError(null);
    setWritePubRefStatus(null);
    try {
      const title = detail?.title?.trim() || "writing piece";
      // Residual (gh): prefer stored highlight; capture live selection at fire.
      let selection = writeResearchPromptText;
      let fromHighlight = Boolean(writeHighlightText.trim());
      let goal = fromHighlight
        ? `Deep-research the highlighted passage from writing piece «${title}»`
        : `Deep-research the writing piece «${title}»`;
      if (typeof window !== "undefined" && window.getSelection) {
        const live = (window.getSelection()?.toString() || "").trim();
        if (live) {
          selection = live.slice(0, 8000);
          fromHighlight = true;
          goal = `Deep-research the highlighted passage from writing piece «${title}»`;
          setWriteHighlightText(selection);
        }
      }
      const refs = parsePublicationRefs(writePubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setWritePubRefStatus(
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
        research_tier: writeResearchTier,
      });
      setWriteDrWindowId(out.window_id);
      onContextNeedsRefresh();
    } catch (e: unknown) {
      setWriteDrError(e instanceof Error ? e.message : String(e));
    } finally {
      setWriteDrBusy(false);
    }
  }

  // ── Home (no piece selected): start one, pick one, or brainstorm. ──
  if (!deliverableId) {
    const htmlDraftBanner = htmlDraftId ? (
      <div
        className="mb-4 space-y-2 rounded border border-ink/20 p-3 font-mono text-[12px] dark:border-bright/20"
        data-testid="write-html-draft-handoff"
        data-view-format="html"
        data-html-draft={htmlDraftId}
        data-load-status={
          htmlDraftBusy ? "loading" : htmlDraftError ? "error" : htmlDraft ? "ready" : "idle"
        }
        role="status"
      >
        <p>
          HTML draft handoff from reading/research: document{" "}
          <code>{htmlDraftId}</code>
          {htmlDraftBusy ? " · loading…" : null}
        </p>
        {htmlDraftError ? (
          <p
            className="text-emperor"
            data-testid="write-html-draft-error"
            role="alert"
          >
            {htmlDraftError}
          </p>
        ) : null}
        {htmlDraft ? (
          <div
            className="space-y-2 border-t border-ink/10 pt-2 dark:border-bright/10"
            data-testid="write-html-draft-loaded"
            data-document-id={htmlDraft.document_id}
          >
            <p data-testid="write-html-draft-title">
              Title: <strong>{htmlDraft.title}</strong>
            </p>
            {/* Residual (fw): preview outline sections that will import on create. */}
            {htmlDraft.outline_sections?.length ? (
              <div
                className="space-y-1"
                data-testid="write-html-draft-section-preview"
                data-section-count={String(htmlDraft.outline_sections.length)}
              >
                <p className="text-[10px] uppercase tracking-wide text-ink-mute dark:text-moonlight">
                  Outline preview (imports on create)
                </p>
                <ol className="list-decimal pl-4 text-[11px]">
                  {htmlDraft.outline_sections.map((s) => (
                    <li
                      key={`${s.section_index}-${s.title}`}
                      data-testid="write-html-draft-section-preview-item"
                      data-heading-level={String(s.heading_level ?? 0)}
                      data-section-index={String(s.section_index)}
                    >
                      <span className="font-semibold">{s.title}</span>
                      {s.heading_level >= 2 ? (
                        <span className="text-ink-mute"> · h{s.heading_level}</span>
                      ) : null}
                      <span className="text-ink-mute">
                        {" "}
                        · {(s.plain_text || "").slice(0, 80)}
                        {(s.plain_text || "").length > 80 ? "…" : ""}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
            <p
              className="max-h-24 overflow-auto text-[11px] text-ink-soft dark:text-moonlight"
              data-testid="write-html-draft-plain-preview"
            >
              {htmlDraft.plain_preview}
            </p>
            <div
              className="prose max-h-32 overflow-auto text-sm"
              data-testid="write-html-draft-html-preview"
              dangerouslySetInnerHTML={{
                __html: sanitizeHostedHtml(htmlDraft.html.slice(0, 4000)),
              }}
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="write-html-draft-use-title"
                className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 dark:border-bright/30"
                onClick={() => setNewTitle(htmlDraft.title_hint)}
              >
                Use draft title
              </button>
              <button
                type="button"
                data-testid="write-html-draft-seed-brainstorm"
                className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 dark:border-bright/30"
                onClick={() => {
                  setBrainstormSeed(htmlDraft.plain_text.slice(0, 8000));
                  setOnRamp("idea");
                }}
              >
                Seed brainstorm from draft
              </button>
              {/* Residual (ft/fu): import lands on create piece (multi-section). */}
              <span
                className="rounded border border-aurora/40 px-2 py-1 text-[11px] text-aurora"
                data-testid="write-html-draft-import-outline"
                data-import-on-create="true"
                data-html-prose="true"
                data-section-count={String(
                  htmlDraft.outline_sections?.length ?? 0,
                )}
                title="Creating a piece below imports HTML prose into nested outline section(s)"
              >
                Imports on create →{" "}
                {htmlDraft.outline_sections?.length ?? 0} section(s) · HTML
                prose
              </span>
            </div>
            <p
              className="text-[10px] text-ink-mute dark:text-moonlight"
              data-testid="write-html-draft-import-deferred"
            >
              Residual (fu): create a piece below (connect research); h1–h3
              structure becomes outline sections with plain-text prose
              (HTML-first, not PDF). Provenance document{" "}
              <code>{htmlDraft.document_id}</code>.
            </p>
            {/* Residual (fp): visible provenance stamp for freeform project type. */}
            <p
              className="text-[10px] font-mono"
              data-testid="write-html-draft-provenance"
              data-document-id={htmlDraft.document_id}
            >
              Provenance freeform:{" "}
              <code>
                {projectType.freeform.trim() ||
                  `html_draft:${htmlDraft.document_id}`}
              </code>
            </p>
          </div>
        ) : null}
      </div>
    ) : null;

    // Residual (pp): twin multi-select draft seed handoff banner.
    const twinSeedBanner =
      twinSeedKey && !deliverableId ? (
        <div
          className="mb-4 space-y-2 rounded border border-ink/20 p-3 font-mono text-[12px] dark:border-bright/20"
          data-testid="write-twin-seed-handoff"
          data-view-format="html"
          data-twin-seed-key={twinSeedKey}
          data-load-status={twinSeed ? "ready" : "missing"}
          data-note-count={
            twinSeed ? String(twinSeed.note_ids.length) : "0"
          }
          data-note-ids={
            twinSeed
              ? twinSeed.note_ids.length <= 6
                ? twinSeed.note_ids.join(",")
                : `${twinSeed.note_ids.slice(0, 6).join(",")},+${twinSeed.note_ids.length - 6}`
              : ""
          }
          data-asset-id={twinSeed?.asset_id ?? ""}
          data-source={twinSeed?.source ?? ""}
          role="status"
        >
          {twinSeed ? (
            <>
              <p data-testid="write-twin-seed-ready">
                Twin draft seed from recursive note-taker:{" "}
                <strong>{twinSeed.title}</strong> · notes=
                {twinSeed.note_ids.length}
                {twinSeed.note_ids.length
                  ? ` · note_ids=${
                      twinSeed.note_ids.length <= 6
                        ? twinSeed.note_ids.join(",")
                        : `${twinSeed.note_ids.slice(0, 6).join(",")},+${twinSeed.note_ids.length - 6}`
                    }`
                  : ""}{" "}
                · source=
                <code data-testid="write-twin-seed-source">
                  {twinSeed.source}
                </code>{" "}
                · asset=
                <code>{twinSeed.asset_id || "(none)"}</code>
              </p>
              <p className="text-[11px] opacity-80">
                Brainstorm seeded with selected twin plain text (sessionStorage;
                HTML-first · not auto-promoted into an outline).
              </p>
              {twinSeed.html ? (
                <div
                  className="prose max-h-28 overflow-auto text-sm border-t border-ink/10 pt-2 dark:border-bright/10"
                  data-testid="write-twin-seed-html-preview"
                  dangerouslySetInnerHTML={{
                    __html: sanitizeHostedHtml(twinSeed.html.slice(0, 4000)),
                  }}
                />
              ) : null}
              <p
                className="text-[10px] font-mono"
                data-testid="write-twin-seed-provenance"
                data-source={twinSeed.source}
              >
                Provenance freeform:{" "}
                <code>
                  {projectType.freeform.trim() ||
                    formatTwinWriteSeedFreeform(twinSeed)}
                </code>
              </p>
            </>
          ) : (
            <p
              className="text-emperor"
              data-testid="write-twin-seed-missing"
              role="alert"
            >
              Twin seed key not found in this session (expired or wrong tab).
              Re-open Draft HTML from Twin notes.
            </p>
          )}
        </div>
      ) : null;

    return (
      // Landing-glass (SPR-03 M2): the Write home is a LANDING surface. The
      // root renders through GlassSurface so the <Scene/> (z-0) shows through;
      // the scrim keeps the heading + the start-a-piece card legible. The card
      // below is glassed too (was an opaque bg-ice-0 dark:bg-charcoal-2 sheet)
      // so the scene reads behind it instead of an ice wall.
      <GlassSurface
        className="mx-auto h-full max-w-3xl overflow-y-auto px-6 py-8"
        data-testid="write-home-mode"
        data-view-format="html"
        data-html-first="true"
        data-product-panel="write_home"
        data-soft-budget="true"
        data-budget-before-fire="true"
        data-never-auto-route="true"
      >
        <header className="mb-6 space-y-2">
          <h1 className="font-serif text-2xl font-semibold text-ink dark:text-bright">
            Write a piece
          </h1>
          <p className="mt-1 text-sm text-ink-soft dark:text-moonlight">
            Pull your research notes into an outline, generate a first draft
            from them, then edit. Or dump a raw idea and let the blocks fall out.
            HTML-first deliverables only (never PDF view). Soft budget foresight
            on driver prompts · never auto-route model choice.
          </p>
          {/* Residual (apx): competitive DR map on Write home (reading ≡ research ≡ writing). */}
          <p
            className="text-[10px] font-mono space-x-2"
            data-testid="write-home-competitive-links"
            data-view-format="html"
            data-html-first="true"
            data-hop-pipeline="api"
            data-stage-pipeline="ape"
            data-offline-surface-count={String(
              competitiveDrOfflineSurfaceCatalog().count,
            )}
            data-live-injectors-deferred="true"
            data-notdiamond-is-router="false"
            role="navigation"
            aria-label="Competitive deep-research scorecard navigation"
          >
            <a
              href="/settings#settings-competitive-dr-scorecard"
              data-testid="write-home-competitive-scorecard-link"
              data-offline-surface-count={String(
                competitiveDrOfflineSurfaceCatalog().count,
              )}
              data-notdiamond-is-router="false"
              className="underline opacity-80 hover:opacity-100"
              title={competitiveDrOfflineSurfaceCatalog().summary}
            >
              Settings · competitive DR
            </a>
            <a
              href={capabilityGuidanceLinks.competitiveQuality}
              data-testid="write-home-competitive-dr-future-agent-link"
              className="underline opacity-80 hover:opacity-100"
              title="Settings competitive deep-research quality status"
            >
              Settings · competitive quality
            </a>
            <span
              className="opacity-70"
              data-testid="write-home-competitive-pipeline-hint"
            >
              hops insights→questions→sources · stages plan→terminal
            </span>
          </p>
          {/* Residual (aqr): soft-budget honesty nav on Write home (parity ResearchThis aqq). */}
          <p
            className="text-[10px] font-mono flex flex-wrap gap-x-3 gap-y-1 opacity-90"
            data-testid="write-home-honesty-nav"
            data-view-format="html"
            data-soft-budget="true"
            data-budget-before-fire="true"
            data-never-auto-route="true"
            role="navigation"
            aria-label="Write home budget and model honesty navigation"
          >
            <a
              href="/settings#prompt-cost-projection"
              data-testid="write-home-prompt-cost-honesty-link"
              className="underline opacity-90 hover:opacity-100"
              title="Settings prompt-cost projection (soft budget foresight)"
            >
              Prompt-cost projection
            </a>
            <a
              href="/settings#decision-tree-panel"
              data-testid="write-home-decision-tree-honesty-link"
              className="underline opacity-90 hover:opacity-100"
              title="Settings decision-tree driver (manual model choice · never auto-route)"
            >
              Decision-tree driver
            </a>
            <span
              className="opacity-70"
              data-testid="write-home-soft-budget-hint"
            >
              soft budget · budget-before-fire · never auto-route
            </span>
          </p>
        </header>

        {htmlDraftBanner}
        {twinSeedBanner}

        <GlassSurface className="mb-6 space-y-3 rounded-md p-3">
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="What are you writing? (a title)"
            className="w-full rounded border border-rule px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
          />
          {/* M4: open-ended project type — presets seed, do not gate. */}
          <ProjectTypeField
            value={projectType}
            onChange={setProjectType}
            disabled={starting}
          />
          {/* M1: the connect-to-research step. Pick a project (imports its
              blocks onto the canvas) or none (auto-spawns + links a folder).
              Either way the piece is created WITH investigation_root_id set. */}
          {newTitle.trim() ? (
            <ConnectResearch
              pieceTitle={newTitle}
              disabled={starting}
              onConnect={(resolved) => void createWithConnection(resolved)}
            />
          ) : (
            <p className="text-xs italic text-ink-mute dark:text-moonlight">
              Name the piece to choose a research project to connect it to.
            </p>
          )}
          {starting && (
            <p className="text-xs text-ocean">Starting your piece…</p>
          )}
          <button
            type="button"
            onClick={() => setOnRamp((v) => (v === "idea" ? null : "idea"))}
            className="text-sm text-ink-soft underline hover:text-ink dark:text-starlight"
          >
            or brainstorm from an idea
          </button>
        </GlassSurface>

        {onRamp === "idea" && (
          <div className="mb-6 rounded-md border border-rule dark:border-charcoal-1">
            <p className="px-4 pt-3 text-xs text-ink-mute dark:text-moonlight">
              Think aloud here. The drivers you confirm become blocks you can
              outline and draft from — start a piece first to land them on it.
            </p>
            <IdeaDump
              sectionId="__brainstorm__"
              initialIdea={brainstormSeed}
            />
          </div>
        )}

        {pieces.length > 0 && (
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-mute dark:text-moonlight">
              Your pieces
            </h2>
            <ul className="space-y-1">
              {pieces.map((p) => (
                <li key={p.deliverable_id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/write/${p.deliverable_id}`)}
                    className="w-full rounded border border-rule bg-ice-0 px-3 py-2 text-left hover:border-ocean dark:border-charcoal-1 dark:bg-charcoal-2"
                  >
                    <span className="font-serif text-ink dark:text-bright">{p.title}</span>
                    <span className="ml-2 text-xs text-ink-mute dark:text-moonlight">
                      {p.section_count} section{p.section_count === 1 ? "" : "s"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </GlassSurface>
    );
  }

  // ── A piece is open: the outline + repository loop. ──
  // Dense-legible-keep-opaque (SPR-03 M3 / rigor #1): the open piece is the
  // dense Write IDE (outline + block repository + canvas). It stays OPAQUE via
  // GlassSurface variant="solid" — same hue at alpha 1, no scene behind to
  // erode contrast. Transparency here would risk the body text M3 protects;
  // the honest choice is solid, exactly like the /inv/:id research IDE.
  return (
    <GlassSurface
      variant="solid"
      className="flex h-full min-h-0"
      data-testid="write-piece-mode"
      data-view-format="html"
      data-html-first="true"
      data-product-panel="write_piece"
      data-deliverable-id={deliverableId || ""}
    >
      <main className="flex min-w-0 flex-1 flex-col px-6 py-5">
        <header className="mb-4 flex items-baseline justify-between gap-3">
          <div className="min-w-0">
            <button
              type="button"
              onClick={() => navigate("/write")}
              className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
            >
              ← all pieces
            </button>
            <h1 className="truncate font-serif text-xl font-semibold text-ink dark:text-bright">
              {detail?.title ?? (loading ? "Opening…" : "Piece")}
            </h1>
            {/* M1: the active research connection is shown at all times. The
                link is the read-back investigation_root_id (it EXISTS in the
                substrate, not a UI claim). */}
            {detail && (
              <p
                data-testid="active-connection"
                className="mt-0.5 text-[11px] text-ink-mute dark:text-moonlight"
              >
                {detail.investigation_root_id ? (
                  <>Connected to research · backing folder linked</>
                ) : (
                  <span className="text-emperor">No research connected</span>
                )}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            {/* Residual (gc): model driver + budget usage on Write piece. */}
            <div data-testid="write-piece-driver-badge" data-view-format="html">
              <DecisionTreeDriverBadge
                researchTier={writeResearchTier}
                /* Residual (ph): project DR selection + pub refs vs daily budget. */
                promptText={composeDriverPromptText(writeResearchPromptText, writePubRefs)}
              />
              {/* Residual (if): Settings deep-link for driver + budget. */}
              <p className="mt-1 text-[11px] font-mono">
                <a
                  href="/settings#decision-tree-panel"
                  data-testid="write-piece-settings-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="Open Settings decision-tree: driver, budget bar, sample cost projection"
                >
                  Settings · driver & budget
                </a>
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* M1: toggle to the imported SPR-03 Canvas of the linked research. */}
              {detail?.investigation_root_id && (
                <button
                  type="button"
                  onClick={() =>
                    setPieceView((v) => (v === "canvas" ? "outline" : "canvas"))
                  }
                  className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
                >
                  {pieceView === "canvas" ? "outline" : "research canvas"}
                </button>
              )}
              <button
                type="button"
                onClick={() =>
                  setOnRamp((v) => (v === "context" ? null : "context"))
                }
                className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
              >
                {onRamp === "context" ? "hide brainstorm" : "brainstorm a section"}
              </button>
            </div>
          </div>
        </header>

        {/* Residual (gd): re-import html_draft into this open piece. */}
        {htmlDraftId ? (
          <div
            className="mb-4 space-y-2 rounded border border-ink/20 p-3 font-mono text-[12px] dark:border-bright/20"
            data-testid="write-piece-html-reimport"
            data-view-format="html"
            data-html-draft={htmlDraftId}
            data-load-status={
              htmlDraftBusy
                ? "loading"
                : htmlDraftError
                  ? "error"
                  : htmlDraft
                    ? "ready"
                    : "idle"
            }
          >
            <p>
              HTML draft re-import: <code>{htmlDraftId}</code>
              {htmlDraftBusy ? " · loading…" : null}
            </p>
            {htmlDraftError ? (
              <p className="text-emperor" role="alert">
                {htmlDraftError}
              </p>
            ) : null}
            {htmlDraft ? (
              <>
                <p data-testid="write-piece-reimport-title">
                  {htmlDraft.title} · {htmlDraft.outline_sections?.length ?? 0}{" "}
                  section(s)
                </p>
                <button
                  type="button"
                  data-testid="write-piece-reimport-run"
                  disabled={reimportBusy || !detail?.deliverable_id}
                  onClick={() => void importIntoOpenPiece()}
                  className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
                >
                  {reimportBusy
                    ? "Importing…"
                    : "Import HTML draft into this piece"}
                </button>
                {reimportStatus ? (
                  <p
                    className="text-[11px]"
                    data-testid="write-piece-reimport-status"
                    role="status"
                  >
                    {reimportStatus}
                  </p>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}

        {onRamp === "context" && (
          <div className="mb-4 rounded-md border border-rule dark:border-charcoal-1">
            <p className="px-4 pt-3 text-xs text-ink-mute dark:text-moonlight">
              The outline-optional path: drop blocks and state an objective,
              then generate directly. No fabricated sources — blocks first.
            </p>
            <ContextWindow />
          </div>
        )}

        {/* Residual (ge): deep research + pub refs on open Write piece. */}
        {detail?.deliverable_id ? (
          <section
            className="mb-4 space-y-2 rounded border border-ink/20 p-3 font-mono text-[12px] dark:border-bright/20"
            data-testid="write-piece-research-launch"
            data-view-format="html"
            data-asset-id={detail.deliverable_id}
            data-from-highlight={writeHighlightText.trim() ? "true" : "false"}
            onMouseUp={captureWriteHighlight}
          >
            <p className="text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight">
              Deep research from this piece
            </p>
            <p className="text-[11px] text-ink-mute dark:text-moonlight">
              Select text in the outline (or here), or research the whole piece.
              Optional arxiv / substack / URL grounding.
            </p>
            {/* Residual (gh): selection preview drives budget projection. */}
            <div
              className="space-y-1"
              data-testid="write-piece-selection-preview"
              data-from-highlight={writeHighlightText.trim() ? "true" : "false"}
            >
              {writeHighlightText.trim() ? (
                <>
                  <p
                    className="max-h-16 overflow-auto text-[11px] text-ink dark:text-bright"
                    data-testid="write-piece-selection-text"
                  >
                    {writeHighlightText.slice(0, 500)}
                    {writeHighlightText.length > 500 ? "…" : ""}
                  </p>
                  <button
                    type="button"
                    className="underline text-[11px]"
                    data-testid="write-piece-clear-highlight"
                    onClick={clearWriteHighlight}
                    disabled={writeDrBusy}
                  >
                    Clear highlight (use whole piece)
                  </button>
                </>
              ) : (
                <p
                  className="text-[11px] text-ink-mute dark:text-moonlight"
                  data-testid="write-piece-selection-fallback"
                >
                  No highlight — budget/launch use whole-piece prompt.
                </p>
              )}
            </div>
            <div
              className="space-y-1"
              data-testid="write-piece-pub-refs"
              data-view-format="html"
              data-offline-default="true"
              data-seamless-pub-quick-call="true"
              data-knowledge-dense-presets={String(
                KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
              )}
            >
              <label
                className="text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight"
                htmlFor="write-piece-refs-input"
              >
                Ground with pubs (optional)
              </label>
              {/* Residual (anv): write-piece DR quick-call (parity MO anu · ResearchThis ahc). */}
              <div
                className="flex flex-wrap gap-1 items-center"
                data-testid="write-piece-publication-quick-call"
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
                    data-testid={`write-piece-preset-${p.id}`}
                    data-preset-id={p.id}
                    data-kind={p.kind}
                    data-reference={p.reference}
                    data-auto-hydrate="false"
                    disabled={writeDrBusy}
                    onClick={() => {
                      const ref = p.reference.trim();
                      if (!ref) return;
                      setWritePubRefs((prev) => {
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
                id="write-piece-refs-input"
                data-testid="write-piece-refs-input"
                value={writePubRefs}
                onChange={(e) => setWritePubRefs(e.target.value)}
                disabled={writeDrBusy}
                rows={2}
                placeholder={"arxiv:1706.03762\nhttps://…"}
                className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
              />
              {/* Residual (anx): L1/L2 hydrate prep deep-links (parity ResearchThis uk). */}
              <p
                className="text-[10px] font-mono space-x-2"
                data-testid="write-piece-pub-refs-prep"
                data-l1-l2-hydrate-prep="true"
                data-offline-honest="true"
              >
                <a
                  href="/settings#hydrate-live-status"
                  data-testid="write-piece-hydrate-settings-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="Settings publication hydrate readiness (arxiv/substack · offline default)"
                >
                  Settings · hydrate readiness
                </a>
                <a
                  href={capabilityGuidanceLinks.arxivHydration}
                  data-testid="write-piece-dual-gate-l1-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="Dual-gate L1 arxiv hydrate checklist (prep only · offline identity default)"
                >
                  Dual-gate L1 arxiv checklist
                </a>
                <a
                  href={capabilityGuidanceLinks.substackAcquisition}
                  data-testid="write-piece-dual-gate-l2-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
                >
                  Dual-gate L2 Substack checklist
                </a>
                <span
                  className="opacity-70"
                  data-testid="write-piece-pub-refs-offline-default"
                  data-offline-honest="true"
                  role="status"
                >
                  offline identity default
                </span>
              </p>
              {writePubRefStatus ? (
                <p
                  className="text-[10px] text-aurora"
                  data-testid="write-piece-refs-status"
                  role="status"
                >
                  {writePubRefStatus}
                </p>
              ) : null}
            </div>
            <div
              data-testid="write-piece-budget-mount"
              data-view-format="html"
              data-research-tier={writeResearchTier}
              data-depth-prefill={writeDepthPrefill}
            >
              <p
                className="text-[11px] font-mono opacity-80"
                data-testid="write-piece-depth-prefill"
                role="status"
              >
                Depth prefill: {writeDepthPrefill}
                {writeDepthPrefill === "installed"
                  ? ` → ${writeResearchTier}`
                  : writeDepthPrefill === "none"
                    ? " (default deep)"
                    : ""}
              </p>
              <ResearchLaunchBudgetPanel
                promptText={composeDriverPromptText(writeResearchPromptText, writePubRefs)}
                researchTier={writeResearchTier}
                allowTierPick
                onResearchTierChange={setWriteResearchTier}
                onProjectionChange={onWriteDrProjectionChange}
              />
            </div>
            {writeBudgetWarn ? (
              <label
                className="flex items-center gap-2 text-[11px] text-emperor"
                data-testid="write-piece-over-budget-warn"
              >
                <input
                  type="checkbox"
                  data-testid="write-piece-force-over-budget"
                  checked={writeForceOverBudget}
                  onChange={(e) => setWriteForceOverBudget(e.target.checked)}
                  disabled={writeDrBusy}
                />
                Force open despite budget projection
              </label>
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                data-testid="write-piece-deep-research"
                disabled={writeDrBusy || (writeBudgetWarn && !writeForceOverBudget)}
                onClick={() => void spinWriteDeepResearch("floating")}
                className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
              >
                {writeDrBusy ? "Opening…" : "Deep research (window)"}
              </button>
              <button
                type="button"
                data-testid="write-piece-deep-research-full"
                disabled={writeDrBusy || (writeBudgetWarn && !writeForceOverBudget)}
                onClick={() => void spinWriteDeepResearch("full")}
                className="rounded border border-ink/30 px-2 py-1 text-[11px] hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
                title="Open deep research expanded to full working region"
              >
                {writeDrBusy ? "Opening…" : "Deep research (full)"}
              </button>
              {writeDrWindowId ? (
                <span
                  className="text-[11px] text-aurora"
                  data-testid="write-piece-research-window-id"
                  role="status"
                >
                  Window {writeDrWindowId}
                </span>
              ) : null}
              {writeDrError ? (
                <span
                  className="text-[11px] text-emperor"
                  role="alert"
                  data-testid="write-piece-research-error"
                >
                  {writeDrError}
                </span>
              ) : null}
            </div>
          </section>
        ) : null}

        {detail ? (
          pieceView === "canvas" && detail.investigation_root_id ? (
            // M1: the SPR-03 Canvas, IMPORTED (not re-implemented) — it loads
            // the linked investigation's insight/question blocks onto the free
            // 2D canvas. Positions persist via the SPR-03 typed-event funnel.
            <div className="min-h-0 flex-1">
              <Canvas investigationId={detail.investigation_root_id} />
            </div>
          ) : (
            <Outline
              deliverableId={detail.deliverable_id}
              sections={detail.sections}
              onChanged={refresh}
              registerAddHandler={registerAddHandler}
              investigationId={detail.investigation_root_id}
            />
          )
        ) : (
          <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
            {loading ? "Opening the piece…" : "That piece isn't available."}
          </p>
        )}

        {/* Residual (ga/gb): twins + research context on writing assets. */}
        {detail?.deliverable_id ? (
          <>
            <section
              className="mt-4 border-t border-rule pt-4 dark:border-charcoal-1"
              data-testid="write-piece-twins-mount"
              data-view-format="html"
              data-asset-id={detail.deliverable_id}
            >
              {/* Residual (gg): remount twins with context refresh key. */}
              <div
                data-testid="write-piece-twins-refresh"
                data-refresh-key={String(contextRefreshKey)}
              >
                <TwinNotesPanel
                  key={`twins-${detail.deliverable_id}-${contextRefreshKey}`}
                  assetId={detail.deliverable_id}
                  spawnId={null}
                  autoLoad
                  autoSeedIfEmpty
                  seedTitle={detail.title || detail.deliverable_id}
                  seedBodyText={detail.title || ""}
                  onPromoted={onContextNeedsRefresh}
                  researchTier={writeResearchTier}
                />
              </div>
            </section>
            <section
              className="mt-4 border-t border-rule pt-4 dark:border-charcoal-1"
              data-testid="write-piece-context-mount"
              data-view-format="html"
              data-asset-id={detail.deliverable_id}
              data-research-tier={writeResearchTier}
              data-seamless-write-context="true"
            >
              <div
                data-testid="write-piece-context-refresh"
                data-refresh-key={String(contextRefreshKey)}
              >
                {/* Residual (amq): Write depth posture into intelligent context. */}
                <ResearchContextPanel
                  key={`ctx-${detail.deliverable_id}-${contextRefreshKey}`}
                  assetId={detail.deliverable_id}
                  spawnId={null}
                  autoLoad
                  researchTier={writeResearchTier}
                />
              </div>
            </section>
            {/* Residual (gf/om): multi-select open + recent DR spawns → this piece. */}
            {availableSpawnIds.length > 0 ? (
              <section
                className="mt-4 border-t border-rule pt-4 dark:border-charcoal-1"
                data-testid="write-piece-collective-mount"
                data-view-format="html"
                data-available-spawn-count={String(availableSpawnIds.length)}
                data-recent-count={String(recentSpawnIds.length)}
                data-asset-id={detail.deliverable_id}
              >
                <CollectiveResearchPanel
                  availableSpawnIds={availableSpawnIds}
                  parentAssetId={detail.deliverable_id}
                  recentSpawnIds={recentSpawnIds}
                  openSpawnIds={openSpawnIds}
                  onDocMerged={onContextNeedsRefresh}
                  onRecentSpawnsCleared={() => setRecentTick((n) => n + 1)}
                />
              </section>
            ) : null}
          </>
        ) : null}
      </main>

      <aside className="hidden w-80 shrink-0 flex-col border-l border-rule bg-ice-0 p-4 dark:border-charcoal-1 dark:bg-charcoal-2 lg:flex">
        <BlockRepository onAdd={(hit) => addHandler.current(hit)} />
      </aside>
    </GlassSurface>
  );
}
