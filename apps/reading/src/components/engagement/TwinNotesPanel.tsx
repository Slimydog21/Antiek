/**
 * TwinNotesPanel — recursive note-taker UI for insights/questions on an asset.
 *
 * Residual (ba): every information asset has a twin substrate of LLM/operator
 * notes. Residual (cq): autoLoad twins on mount for DR/hosted windows.
 * Residual (dd): autoSeedIfEmpty — offline seed when load finds zero notes so
 * the recursive note-taker substrate exists without a manual click.
 * Residual (ea): autoPromoteAfterLoad — promote twins into research context
 * after autoLoad/seed so prompts inherit recursive notes without a click.
 * Residual (fk): twin-notes-metrics data attributes for recursive note-taker
 * audit (parity ResearchContextPanel ff).
 * Residual (hh): offline-seed honesty — machine-readable live_seed /
 * seed_source / offline_honest on seed status (parity ResearchContext hydrate hd).
 * Residual (hi): twin-promote-metrics data attributes for promote→context
 * audit (parity twin-notes-metrics fk / context-search-metrics fi).
 * Residual (ib): Settings deep-link for twin seed live readiness (hs).
 * Residual (kr): optional researchTier chrome for depth posture on note-taker.
 * Residual (lb): fall back to seed/list API research_tier when prop absent (la).
 * Residual (mq): selective promote by twin kind (all | insight | question)
 * for recursive note-taker merge UX into research context.
 * Residual (mr): list filter by twin kind (browse insights/questions before
 * selective promote) — same kind axis as promoteKinds.
 * Residual (ms): "Promote visible" one-click — align promoteKinds to listFilter
 * then promote (browse→merge path without a second dropdown).
 * Residual (mt): dual-gate L1–L4 checklist deep-link for L3 twin live seed prep
 * (parity mj/ml/mm; never enables injectors).
 * Residual (mx): multi-select by note_id — promote only checked twin notes.
 * Residual (my): clear multi-select after successful note_ids promote; echo
 * note_ids on promote metrics for audit honesty.
 * Residual (mz): chase selected twin notes as floating deep research
 * (highlight→float DR parity for recursive note-taker questions/insights).
 * Residual (na): budget soft-gate on twin chase (parity marketplace iy) —
 * ResearchLaunchBudgetPanel + force override when projection would exceed.
 * Residual (nc): DecisionTreeDriverBadge + chase metrics (model/spawn/tier)
 * for model+budget+depth audit on recursive note-taker chase path.
 * Residual (qi): DecisionTreeDriverBadge promptText from chase selection preview.
 * Residual (nd): one-click select questions|insights into multi-select
 * (chase/promote questions path without manual checkbox grind).
 * Residual (ne): invert multi-select over currently visible notes.
 * Residual (ni): note_ids provenance in chase goal_hint (recursive audit).
 * Residual (oe): chase success notes spawn is in recent ring for collective
 * multi-select even if the floating window is closed (parity ob).
 * Residual (pn): open multi-selected twins as HTML draft window (FUTURE-AGENT
 * V1 partial — recursive note-taker combine draft before promote/merge).
 * Residual (po): twin-draft-metrics machine attrs after HTML draft open
 * (note_count / note_ids / window_id) for recursive note-taker audit.
 * Residual (pp): twin multi-select → Write handoff via sessionStorage twin_seed
 * (brainstorm seed + HTML preview; no invented server document_id).
 * Residual (acq): data-write-seed-has-body on twin draft + promote Open Write
 * (true when note/unit body text non-empty; parity ResearchProgress acp).
 * Residual (adi): twin-draft-metrics data-research-tier for depth audit on
 * recursive note-taker HTML draft path (prop/API tier; parity chase metrics).
 * Residual (adl): twin-promote-metrics data-research-tier for promote→context
 * depth audit (parity draft adi / chase).
 * Residual (ps): twin HTML draft full working-region window (parity chase full).
 * Residual (pt): twin-draft-metrics echo note_ids provenance (parity ni chase).
 * Residual (pw): mergeTwinChaseNotes pure helper — dedupe by note_id, questions
 * first (FUTURE-AGENT V1 cross-asset combine foundation).
 * Residual (px): second asset_id picker — load remote twins + multi-select +
 * mergeTwinChaseNotes → openTwinDraft float|full + Write seed (full V1 UI).
 * Residual (qb): accumulate N>2 merge assets (add another asset_id without
 * replacing prior) → mergeTwinChaseNotes over primary + all buckets.
 * Residual (rr): Open Write twin_seed after promote → context (promoted units).
 * HTML-first; never PDF.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchTwinNotes,
  promoteTwinsToContext,
  recordTwinNote,
  seedTwinNotes,
  type TwinNotesResponse,
  type TwinPromoteContextResponse,
} from "../../api/engagement";
import { launchFloatingDeepResearch } from "../../modes/Reading/launchFloatingDeepResearch";
import {
  buildTwinPromoteWriteHref,
  buildTwinWriteHref,
  plainTextFromHtml,
  storeTwinWriteSeed,
} from "../../workspace/twinWriteSeed";
import { openWindow } from "../windows/openWindow";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "./ResearchLaunchBudgetPanel";

/** Minimal twin note shape for residual (mz) chase payload. */
export type TwinChaseNote = {
  note_id: string;
  kind: string;
  text: string;
};

/**
 * Residual (mz): pure helper — build selection_text + goal_hint for floating
 * deep research from multi-selected twin notes (questions preferred first).
 */
export function buildTwinChasePayload(
  notes: TwinChaseNote[],
  assetId: string,
): { selection_text: string; goal_hint: string; note_ids: string[] } {
  const ordered = [...notes].sort((a, b) => {
    // Prefer questions (chase open questions) then insights then other.
    const rank = (k: string) =>
      k === "question" ? 0 : k === "insight" ? 1 : 2;
    return rank(a.kind) - rank(b.kind);
  });
  const note_ids = ordered.map((n) => n.note_id);
  const lines = ordered.map(
    (n) => `[${n.kind}] ${String(n.text || "").trim()}`.trim(),
  );
  const selection_text = lines.filter(Boolean).join("\n\n");
  const qCount = ordered.filter((n) => n.kind === "question").length;
  const iCount = ordered.filter((n) => n.kind === "insight").length;
  // Residual (ni): include note_ids in goal_hint for recursive provenance.
  const idsPreview =
    note_ids.length <= 4
      ? note_ids.join(",")
      : `${note_ids.slice(0, 4).join(",")},+${note_ids.length - 4}`;
  const goal_hint =
    `Twin chase on ${assetId.trim() || "asset"}: ` +
    `${ordered.length} note(s) (questions=${qCount}, insights=${iCount})` +
    (idsPreview ? ` · note_ids=${idsPreview}` : "");
  return { selection_text, goal_hint, note_ids };
}

/**
 * Residual (pw): pure helper — merge twin note lists from one or more assets
 * for cross-asset combine drafts. Dedupes by note_id (first wins); orders
 * questions before insights. Never invents notes.
 */
export function mergeTwinChaseNotes(
  lists: readonly (readonly TwinChaseNote[])[],
): TwinChaseNote[] {
  const seen = new Set<string>();
  const out: TwinChaseNote[] = [];
  for (const list of lists) {
    for (const n of list) {
      const id = String(n?.note_id || "").trim();
      if (!id || seen.has(id)) continue;
      const text = String(n?.text || "").trim();
      if (!text) continue;
      seen.add(id);
      out.push({
        note_id: id,
        kind: String(n.kind || "note").trim() || "note",
        text,
      });
    }
  }
  return out.sort((a, b) => {
    const rank = (k: string) =>
      k === "question" ? 0 : k === "insight" ? 1 : 2;
    return rank(a.kind) - rank(b.kind);
  });
}

/**
 * Residual (pn): pure helper — build HTML draft document from multi-selected
 * twin notes (questions first). Escapes text; never invents content.
 */
export function buildTwinDraftHtml(
  notes: TwinChaseNote[],
  assetId: string,
): { html: string; title: string; note_ids: string[] } {
  const ordered = [...notes].sort((a, b) => {
    const rank = (k: string) =>
      k === "question" ? 0 : k === "insight" ? 1 : 2;
    return rank(a.kind) - rank(b.kind);
  });
  const note_ids = ordered.map((n) => n.note_id);
  const aid = (assetId || "").trim() || "asset";
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  const items = ordered
    .map((n) => {
      const kind = escape(n.kind || "note");
      const text = escape(String(n.text || "").trim());
      const id = escape(n.note_id);
      return `<li data-note-id="${id}" data-kind="${kind}"><strong>${kind}</strong>: ${text}</li>`;
    })
    .join("\n");
  const title = `Twin draft · ${aid} · ${ordered.length} note(s)`;
  const html =
    `<article data-view-format="html" data-twin-draft="true" data-asset-id="${escape(aid)}" data-note-count="${ordered.length}">` +
    `<h1>${escape(title)}</h1>` +
    `<p class="meta">Recursive note-taker draft (propose-only combine · not auto-promoted into context).</p>` +
    `<ul class="twin-draft-notes">\n${items}\n</ul>` +
    `</article>`;
  return { html, title, note_ids };
}

export type TwinNotesPanelProps = {
  assetId: string;
  spawnId?: string | null;
  /** Residual (cq): fetch twin notes on mount. */
  autoLoad?: boolean;
  /**
   * Residual (dd): when autoLoad finds note_count=0, call offline twin seed.
   * Does not invent live LLM content; force_offline seed only.
   */
  autoSeedIfEmpty?: boolean;
  /** Optional title/body context for offline seed. */
  seedTitle?: string | null;
  seedBodyText?: string | null;
  /**
   * Residual (ea): after autoLoad (and optional seed), promote twins into
   * research context units when notes exist. Offline-safe promote path.
   */
  autoPromoteAfterLoad?: boolean;
  /**
   * Residual (ec): notify parent after a successful promote so research
   * context panels can remount/reload with recursive notes.
   */
  onPromoted?: (result: TwinPromoteContextResponse) => void;
  /**
   * Residual (kr): closed research tier for depth posture chrome when parent
   * session/host knows spawn identity (fast|deep|wrestle).
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function TwinNotesPanel({
  assetId,
  spawnId = null,
  autoLoad = false,
  autoSeedIfEmpty = false,
  seedTitle = null,
  seedBodyText = null,
  autoPromoteAfterLoad = false,
  onPromoted,
  researchTier = null,
}: TwinNotesPanelProps) {
  const [twins, setTwins] = useState<TwinNotesResponse | null>(null);
  const [promoted, setPromoted] = useState<TwinPromoteContextResponse | null>(
    null,
  );
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"insight" | "question">("insight");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seedStatus, setSeedStatus] = useState<string | null>(null);
  /** Residual (hh): machine-readable offline-seed honesty (parity hydrate hd). */
  const [seedHonesty, setSeedHonesty] = useState<{
    liveSeed: boolean;
    offlineHonest: boolean;
    seeded: boolean;
    seedSource: string;
    seedSkipped: string | null;
  } | null>(null);
  const [promoteStatus, setPromoteStatus] = useState<string | null>(null);
  /** Residual (mz): chase-selected deep research status chrome. */
  const [chaseStatus, setChaseStatus] = useState<string | null>(null);
  /** Residual (po/pp/px/acq/adi): last twin HTML draft open + Write handoff metrics. */
  const [draftMetrics, setDraftMetrics] = useState<{
    note_count: number;
    note_ids: string[];
    window_id: string | null;
    title: string;
    write_href: string | null;
    write_seed_key: string | null;
    /** Residual (acq): twin_seed body honesty (note text / HTML body non-empty). */
    write_seed_has_body?: boolean;
    /** Residual (adi): depth posture on draft metrics (prop/API research_tier). */
    research_tier?: string | null;
    /** Residual (px): cross-asset merge provenance when draft used second asset. */
    merge_asset_ids?: string[] | null;
    merge_source?: string | null;
  } | null>(null);
  /**
   * Residual (px/qb): merge asset_id input + N loaded buckets (qb accumulates).
   * Each bucket holds its own multi-select; Load updates-or-appends by asset_id.
   */
  const [mergeAssetIdInput, setMergeAssetIdInput] = useState("");
  const [mergeBuckets, setMergeBuckets] = useState<
    {
      asset_id: string;
      twins: TwinNotesResponse;
      selectedNoteIds: string[];
    }[]
  >([]);
  const [mergeLoadStatus, setMergeLoadStatus] = useState<string | null>(null);
  /** Last focused merge asset (UI list + chrome); derived from buckets. */
  const mergeAssetId = mergeBuckets.length
    ? mergeBuckets[mergeBuckets.length - 1]!.asset_id
    : null;
  const mergeTwins = mergeBuckets.length
    ? mergeBuckets[mergeBuckets.length - 1]!.twins
    : null;
  const mergeSelectedNoteIds = useMemo(() => {
    const s = new Set<string>();
    for (const b of mergeBuckets) {
      for (const id of b.selectedNoteIds) s.add(id);
    }
    return s;
  }, [mergeBuckets]);
  /**
   * Residual (nc): machine-readable last chase result for audit (parity
   * twin-promote-metrics / marketplace-host-dr-status).
   */
  const [chaseMetrics, setChaseMetrics] = useState<{
    spawnId: string;
    sessionId: string;
    modelId: string | null;
    researchTier: string;
    viewMode: string;
    noteIdCount: number;
    /** Residual (ni): promoted note_ids for provenance. */
    noteIds: string[];
    forceBudget: boolean;
    viewFormat: string;
    /** Residual (nw): Antiek-bench usage source/task_class when recorded. */
    usageSource: string | null;
    usageTaskClass: string | null;
  } | null>(null);
  /**
   * Residual (na): soft budget gate before twin chase launch.
   * wouldExceed → warn + require force checkbox (never invent $0).
   */
  const [chaseBudgetWarn, setChaseBudgetWarn] = useState(false);
  const [chaseForceBudget, setChaseForceBudget] = useState(false);
  /**
   * Residual (na): chase depth tier for budget projection (defaults from
   * researchTier prop / deep).
   */
  const [chaseTier, setChaseTier] = useState<ResearchLaunchTier>("deep");
  /**
   * Residual (mq): which twin kinds to promote into context.
   * all → both; insight|question → single-class selective merge.
   */
  const [promoteKinds, setPromoteKinds] = useState<
    "all" | "insight" | "question"
  >("all");
  /**
   * Residual (mr): which twin kinds to show in the list (browse filter).
   * Independent of promoteKinds so operators can audit one class then promote it.
   */
  const [listFilter, setListFilter] = useState<
    "all" | "insight" | "question"
  >("all");
  /**
   * Residual (mx): multi-select twin note_ids for per-note promote.
   * Empty selection → promote uses kinds filter only (mq/ms behavior).
   */
  const [selectedNoteIds, setSelectedNoteIds] = useState<Set<string>>(
    () => new Set(),
  );

  // Residual (kr/lb): prop wins; seed/list API research_tier is fallback.
  const apiResearchTier = (twins?.research_tier || "").trim().toLowerCase() || "";
  const normalizedResearchTier =
    (researchTier || "").trim().toLowerCase() || apiResearchTier;

  // Residual (na): prefill chase tier from host researchTier when closed-set.
  useEffect(() => {
    const t = (normalizedResearchTier || "").trim().toLowerCase();
    if (t === "fast" || t === "deep" || t === "wrestle") {
      setChaseTier(t);
    }
  }, [normalizedResearchTier]);

  // Residual (na): clear force when selection empties (fresh batch honesty).
  useEffect(() => {
    if (selectedNoteIds.size === 0) {
      setChaseForceBudget(false);
      setChaseBudgetWarn(false);
    }
  }, [selectedNoteIds.size]);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      let t = await fetchTwinNotes(assetId, {
        includeHtml: true,
        // Residual (le): scope list research_tier when spawn known.
        spawnId: spawnId,
      });
      if (t.view_format !== "html") {
        throw new Error("twin notes view_format must be html");
      }
      // Residual (dd): offline seed when empty so every asset has a twin twin.
      // Panel always force_offline — never invents live LLM note_taker content.
      if (autoSeedIfEmpty && (t.note_count ?? 0) === 0) {
        try {
          const seeded = await seedTwinNotes({
            asset_id: assetId,
            title: seedTitle?.trim() || assetId,
            body_text: seedBodyText?.trim() || "",
            source_spawn_id: spawnId,
            include_html: true,
            force_offline: true,
          });
          if (seeded.view_format !== "html") {
            throw new Error("twin seed view_format must be html");
          }
          // Residual (hh): honor backend live_seed/seed_source; panel force_offline
          // means offline_honest=true unless API reports live_seed (should not
          // happen with force_offline — still surface honestly if it does).
          const liveSeed = Boolean(seeded.live_seed);
          const offlineHonest = !liveSeed;
          const seedSource =
            (seeded.seed_source && String(seeded.seed_source)) ||
            (liveSeed
              ? "engagement_spine.twin.seed_twins_for_asset.live"
              : "engagement_spine.twin.seed_twins_for_asset");
          setSeedHonesty({
            liveSeed,
            offlineHonest,
            seeded: Boolean(seeded.seeded),
            seedSource,
            seedSkipped: seeded.seed_skipped ?? null,
          });
          if (seeded.seeded) {
            setSeedStatus(
              offlineHonest
                ? "Seed mode: offline-honest identity stubs — recursive note-taker substrate (not live note_taker)"
                : "Seed mode: live note_taker injector landed",
            );
          } else {
            setSeedStatus(
              `seed skipped: ${seeded.seed_skipped || "none"}`,
            );
          }
          t = seeded;
        } catch (seedErr) {
          setSeedHonesty(null);
          setSeedStatus(
            seedErr instanceof Error
              ? `seed failed: ${seedErr.message}`
              : "seed failed",
          );
        }
      }
      setTwins(t);
      // Residual (ea): promote seeded/loaded twins into context for prompts.
      if (autoPromoteAfterLoad && (t.note_count ?? 0) > 0) {
        try {
          const p = await promoteTwinsToContext({
            asset_id: assetId,
            include_html: true,
          });
          if (p.view_format !== "html") {
            throw new Error("twin promote view_format must be html");
          }
          setPromoted(p);
          setPromoteStatus(
            `auto-promoted ${p.promoted_count ?? t.note_count} twin unit(s) to context`,
          );
          onPromoted?.(p);
        } catch (pe) {
          setPromoteStatus(
            pe instanceof Error
              ? `auto-promote failed: ${pe.message}`
              : "auto-promote failed",
          );
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [
    assetId,
    autoSeedIfEmpty,
    seedTitle,
    seedBodyText,
    spawnId,
    autoPromoteAfterLoad,
    onPromoted,
  ]);

  useEffect(() => {
    if (!autoLoad || !assetId.trim()) return;
    void load();
    // Mount-once per asset when autoLoad is on (residual cq/dd/ea).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, assetId, autoSeedIfEmpty, autoPromoteAfterLoad]);

  const record = useCallback(async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const t = await recordTwinNote({
        asset_id: assetId,
        kind,
        text: text.trim(),
        source_spawn_id: spawnId,
        include_html: true,
      });
      if (t.view_format !== "html") {
        throw new Error("twin notes view_format must be html");
      }
      setTwins(t);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId, kind, text, spawnId]);

  /** Residual (mr): notes visible under list filter. */
  const visibleNotes = useMemo(() => {
    const notes = twins?.notes || [];
    if (listFilter === "all") return notes;
    return notes.filter((n) => n.kind === listFilter);
  }, [twins?.notes, listFilter]);

  /** Residual (mx): toggle note_id in multi-select set. */
  const toggleNoteSelected = useCallback((noteId: string) => {
    setSelectedNoteIds((prev) => {
      const next = new Set(prev);
      if (next.has(noteId)) next.delete(noteId);
      else next.add(noteId);
      return next;
    });
  }, []);

  /** Residual (mx): select all currently visible notes. */
  const selectAllVisible = useCallback(() => {
    setSelectedNoteIds((prev) => {
      const next = new Set(prev);
      for (const n of visibleNotes) next.add(n.note_id);
      return next;
    });
  }, [visibleNotes]);

  /**
   * Residual (nd): select all notes of a kind from the full twin substrate
   * (not only list-filtered), so operators can multi-select questions for
   * chase/promote without toggling list filter first.
   */
  const selectByKind = useCallback(
    (kindFilter: "question" | "insight") => {
      const notes = twins?.notes || [];
      setSelectedNoteIds((prev) => {
        const next = new Set(prev);
        for (const n of notes) {
          if (n.kind === kindFilter) next.add(n.note_id);
        }
        return next;
      });
    },
    [twins?.notes],
  );

  const clearNoteSelection = useCallback(() => {
    setSelectedNoteIds(new Set());
  }, []);

  /**
   * Residual (ne): invert multi-select for currently visible notes only
   * (list-filter-aware). Notes outside visible set keep prior selection.
   */
  const invertVisibleSelection = useCallback(() => {
    setSelectedNoteIds((prev) => {
      const next = new Set(prev);
      for (const n of visibleNotes) {
        if (next.has(n.note_id)) next.delete(n.note_id);
        else next.add(n.note_id);
      }
      return next;
    });
  }, [visibleNotes]);

  const promote = useCallback(
    async (
      kindsOverride?: "all" | "insight" | "question",
      noteIdsOverride?: string[] | null,
    ) => {
      setBusy(true);
      setError(null);
      try {
        const effective = kindsOverride ?? promoteKinds;
        if (kindsOverride && kindsOverride !== promoteKinds) {
          setPromoteKinds(kindsOverride);
        }
        // Residual (mq): selective kinds for recursive note-taker merge.
        const kinds =
          effective === "all"
            ? null
            : ([effective] as Array<"insight" | "question">);
        // Residual (mx): multi-select note_ids when provided / selected.
        const fromOverride =
          noteIdsOverride !== undefined
            ? noteIdsOverride
            : selectedNoteIds.size > 0
              ? Array.from(selectedNoteIds)
              : null;
        const note_ids =
          fromOverride && fromOverride.length > 0 ? fromOverride : null;
        const p = await promoteTwinsToContext({
          asset_id: assetId,
          include_html: true,
          kinds,
          note_ids,
        });
        if (p.view_format !== "html") {
          throw new Error("twin promote view_format must be html");
        }
        setPromoted(p);
        // Residual (my): after multi-select promote, clear selection so the
        // browse→select→merge loop is ready for the next batch (honest UX).
        if (note_ids && note_ids.length > 0) {
          setSelectedNoteIds(new Set());
        }
        const kindLabel = effective === "all" ? "all kinds" : effective;
        const echoedIds =
          Array.isArray(p.note_ids) && p.note_ids.length > 0
            ? p.note_ids
            : note_ids;
        const selLabel =
          echoedIds && echoedIds.length > 0
            ? ` · selected=${echoedIds.length}`
            : "";
        setPromoteStatus(
          `promoted ${p.promoted_count} twin unit(s) to context (${kindLabel}${selLabel})`,
        );
        onPromoted?.(p);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [assetId, onPromoted, promoteKinds, selectedNoteIds],
  );

  /** Residual (ms): promote using current list filter (browse→merge). */
  const promoteVisible = useCallback(() => {
    void promote(listFilter);
  }, [promote, listFilter]);

  /** Residual (mx): promote only multi-selected note_ids. */
  const promoteSelected = useCallback(() => {
    if (selectedNoteIds.size < 1) {
      setError("Select at least one twin note to promote");
      return;
    }
    void promote(undefined, Array.from(selectedNoteIds));
  }, [promote, selectedNoteIds]);

  /** Residual (mz): selected twin notes resolved from current substrate. */
  const selectedNotes = useMemo(() => {
    const notes = twins?.notes || [];
    if (selectedNoteIds.size < 1) return [] as TwinChaseNote[];
    return notes
      .filter((n) => selectedNoteIds.has(n.note_id))
      .map((n) => ({
        note_id: n.note_id,
        kind: n.kind,
        text: n.text,
      }));
  }, [twins?.notes, selectedNoteIds]);

  /** Residual (na): selection_text preview for budget projection. */
  const chasePromptPreview = useMemo(() => {
    if (selectedNotes.length < 1) return "";
    return buildTwinChasePayload(selectedNotes, assetId).selection_text;
  }, [selectedNotes, assetId]);

  /**
   * Residual (px/qb): notes from all merge buckets (selected only).
   * Order follows bucket load order then note list order within each.
   */
  const mergeSelectedNotes = useMemo(() => {
    const out: TwinChaseNote[] = [];
    for (const b of mergeBuckets) {
      const sel = new Set(b.selectedNoteIds);
      for (const n of b.twins.notes || []) {
        if (!sel.has(n.note_id)) continue;
        out.push({
          note_id: n.note_id,
          kind: n.kind,
          text: n.text,
        });
      }
    }
    return out;
  }, [mergeBuckets]);

  /**
   * Residual (px/qb): load twins for a merge asset_id (must differ from current
   * and may accumulate — qb does not replace prior buckets).
   * Auto-selects all loaded notes for merge convenience.
   */
  const loadMergeAsset = useCallback(async () => {
    const id = mergeAssetIdInput.trim();
    if (!id) {
      setError("Enter a second asset_id to load for cross-asset merge");
      return;
    }
    if (id === (assetId || "").trim()) {
      setError("Merge asset_id must differ from the current asset");
      return;
    }
    setBusy(true);
    setError(null);
    setMergeLoadStatus(null);
    try {
      const t = await fetchTwinNotes(id, { includeHtml: true });
      if (t.view_format !== "html") {
        throw new Error("merge-asset twin notes view_format must be html");
      }
      const ids = (t.notes || [])
        .map((n) => String(n.note_id || "").trim())
        .filter(Boolean);
      setMergeBuckets((prev) => {
        const without = prev.filter((b) => b.asset_id !== id);
        return [
          ...without,
          { asset_id: id, twins: t, selectedNoteIds: ids },
        ];
      });
      // Bucket total is machine-readable on data-merge-asset-count (re-render).
      setMergeLoadStatus(
        `Loaded ${t.note_count ?? ids.length} twin(s) from merge asset ${id}`,
      );
      setMergeAssetIdInput("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [mergeAssetIdInput, assetId]);

  const toggleMergeNoteSelection = useCallback(
    (noteId: string, forAssetId?: string) => {
      const aid =
        (forAssetId || "").trim() ||
        mergeBuckets[mergeBuckets.length - 1]?.asset_id ||
        "";
      if (!aid) return;
      setMergeBuckets((prev) =>
        prev.map((b) => {
          if (b.asset_id !== aid) return b;
          const has = b.selectedNoteIds.includes(noteId);
          return {
            ...b,
            selectedNoteIds: has
              ? b.selectedNoteIds.filter((x) => x !== noteId)
              : [...b.selectedNoteIds, noteId],
          };
        }),
      );
    },
    [mergeBuckets],
  );

  const clearMergeNoteSelection = useCallback(() => {
    setMergeBuckets((prev) =>
      prev.map((b) => ({ ...b, selectedNoteIds: [] })),
    );
  }, []);

  const selectAllMergeNotes = useCallback(() => {
    setMergeBuckets((prev) =>
      prev.map((b) => ({
        ...b,
        selectedNoteIds: (b.twins.notes || [])
          .map((n) => String(n.note_id || "").trim())
          .filter(Boolean),
      })),
    );
  }, []);

  const removeMergeBucket = useCallback((id: string) => {
    setMergeBuckets((prev) => prev.filter((b) => b.asset_id !== id));
  }, []);

  /**
   * Residual (pn/pp/ps/px/qb): open twins as HTML draft window (floating | full)
   * + Write twin_seed handoff. Single-asset uses primary multi-select; cross-
   * asset merges primary + all merge buckets via mergeTwinChaseNotes.
   */
  const openTwinDraft = useCallback(
    (
      mode: "floating" | "full" = "floating",
      opts?: { crossAsset?: boolean },
    ) => {
      const crossAsset = opts?.crossAsset === true;
      let selected: TwinChaseNote[];
      let draftAssetLabel: string;
      let source: string;
      let mergeIds: string[] | null = null;

      if (crossAsset) {
        if (mergeBuckets.length < 1) {
          setError("Load a second asset_id before cross-asset merge draft");
          return;
        }
        const lists: TwinChaseNote[][] = [selectedNotes, mergeSelectedNotes];
        selected = mergeTwinChaseNotes(lists);
        if (selected.length < 1) {
          setError(
            "Select at least one twin note from primary and/or merge asset",
          );
          return;
        }
        if (selectedNotes.length < 1 || mergeSelectedNotes.length < 1) {
          setError(
            "Cross-asset merge requires at least one selected note on primary and merge assets",
          );
          return;
        }
        const primaryId = (assetId || "").trim() || "asset";
        const secondaryIds = mergeBuckets.map((b) => b.asset_id);
        draftAssetLabel = [primaryId, ...secondaryIds].join("+");
        source = "twin_cross_asset_merge";
        mergeIds = [primaryId, ...secondaryIds];
      } else {
        selected = selectedNotes;
        if (selected.length < 1) return;
        draftAssetLabel = assetId;
        source = "twin_draft_selected";
      }

      const draft = buildTwinDraftHtml(selected, draftAssetLabel);
      // Residual (px): stamp merge provenance on HTML article when cross-asset.
      const html =
        crossAsset && mergeIds
          ? draft.html.replace(
              'data-twin-draft="true"',
              `data-twin-draft="true" data-source="${source}" data-merge-assets="${mergeIds.join("|")}"`,
            )
          : draft.html;
      const chase = buildTwinChasePayload(selected, draftAssetLabel);
      const idSuffix = mode === "full" ? ":full" : "";
      const winId = openWindow(
        "hosted_html_document",
        {
          document_id: `twin_draft_${(draftAssetLabel || "asset").replace(/\+/g, "_")}_${Date.now()}`,
          title: draft.title,
          html,
          view_format: "html",
          source,
        },
        {
          id: `win:twin-draft:${(draftAssetLabel || "asset").replace(/\+/g, "_")}:${draft.note_ids.slice(0, 3).join("-")}${idSuffix}`,
          title: draft.title,
          mode,
        },
      );
      // Residual (vd): pass source so cross-asset merge does not collapse to twin_draft_selected.
      const seedKey = storeTwinWriteSeed({
        plain_text: chase.selection_text,
        html,
        title: draft.title,
        asset_id: draftAssetLabel,
        note_ids: draft.note_ids,
        source: source as
          | "twin_draft_selected"
          | "twin_cross_asset_merge",
      });
      const writeHref = seedKey ? buildTwinWriteHref(seedKey) : null;
      // Residual (acq): body honesty — note selection text or stripped HTML body.
      const hasBody = Boolean(
        String(chase.selection_text || "").trim() ||
          plainTextFromHtml(html || "").trim(),
      );
      setDraftMetrics({
        note_count: selected.length,
        note_ids: draft.note_ids,
        window_id: winId,
        title: draft.title,
        write_href: writeHref,
        write_seed_key: seedKey,
        write_seed_has_body: hasBody,
        // Residual (adi): stamp host/API research_tier for draft depth audit.
        research_tier: normalizedResearchTier || null,
        merge_asset_ids: mergeIds,
        merge_source: crossAsset ? source : null,
      });
      setChaseStatus(
        winId
          ? crossAsset
            ? `Opened cross-asset twin HTML draft (${selected.length} note(s) · ${draftAssetLabel}) · mode=${mode}` +
              (writeHref ? " · Write handoff ready" : "")
            : `Opened twin HTML draft (${selected.length} note(s)) · mode=${mode}` +
              (writeHref ? " · Write handoff ready" : "")
          : "Twin HTML draft open failed",
      );
    },
    [selectedNotes, mergeSelectedNotes, mergeBuckets, assetId],
  );

  /**
   * Residual (mz/na): spin floating deep research from multi-selected twins
   * (questions preferred in payload order). Soft-gates on budget projection.
   * Clears selection on success.
   */
  const chaseSelected = useCallback(
    async (viewMode: "floating" | "full" = "floating") => {
      if (selectedNotes.length < 1) {
        setError("Select at least one twin note to chase as deep research");
        return;
      }
      // Residual (na): soft budget gate (parity marketplace iy).
      if (chaseBudgetWarn && !chaseForceBudget) {
        setError(
          "Budget projection may exceed daily cap — check Force chase despite budget, or lower depth tier",
        );
        return;
      }
      setBusy(true);
      setError(null);
      setChaseStatus(null);
      try {
        const payload = buildTwinChasePayload(selectedNotes, assetId);
        if (!payload.selection_text.trim()) {
          throw new Error("Selected twin notes have empty text");
        }
        const forced = chaseBudgetWarn && chaseForceBudget;
        const out = await launchFloatingDeepResearch({
          asset_id: assetId,
          selection_text: payload.selection_text,
          goal_hint: payload.goal_hint,
          view_mode: viewMode,
          research_tier: chaseTier,
        });
        if (out.view_format !== "html") {
          throw new Error("twin chase view_format must be html");
        }
        setSelectedNoteIds(new Set());
        setChaseForceBudget(false);
        // Residual (nc): structured chase metrics for model+spawn audit.
        const usage = out.usage_event ?? null;
        setChaseMetrics({
          spawnId: out.spawn_id,
          sessionId: out.session_id,
          modelId: out.model_id ?? null,
          researchTier: String(out.research_tier || chaseTier),
          viewMode,
          noteIdCount: payload.note_ids.length,
          noteIds: payload.note_ids,
          forceBudget: forced,
          viewFormat: out.view_format,
          usageSource: usage?.source ?? null,
          usageTaskClass: usage?.task_class ?? null,
        });
        const modelLabel = out.model_id?.trim()
          ? ` · model=${out.model_id.trim()}`
          : " · model=none";
        const usageLabel =
          usage?.source || usage?.task_class
            ? ` · bench=${usage?.source ?? "usage"}/${usage?.task_class ?? "?"}`
            : "";
        // Residual (oe): closed-window collective multi-select path honesty.
        const collectiveLabel =
          " · collective=recent_ring (survives window close)";
        setChaseStatus(
          `chased ${payload.note_ids.length} twin note(s) → spawn=${out.spawn_id} · ` +
            `mode=${viewMode} · tier=${out.research_tier}${modelLabel}${usageLabel}` +
            collectiveLabel +
            (forced ? " · force_budget" : ""),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [
      assetId,
      chaseBudgetWarn,
      chaseForceBudget,
      chaseTier,
      selectedNotes,
    ],
  );

  return (
    <section
      className="twin-notes-panel"
      data-testid="twin-notes-panel"
      data-view-format="html"
      data-research-tier={normalizedResearchTier}
      aria-label="Twin notes"
    >
      <header>
        <h2>Twin notes</h2>
        <p className="meta">
          Recursive note-taker for asset <code>{assetId}</code>
          {normalizedResearchTier ? (
            <>
              {" "}
              · tier <code>{normalizedResearchTier}</code>
            </>
          ) : null}
        </p>
        {/* Residual (ib/mt): Settings + dual-gate checklist (L3 twin live seed prep). */}
        <p className="meta font-mono text-[11px] space-x-3">
          <a
            href="/settings#twin-seed-live-status"
            data-testid="twin-notes-settings-link"
            title="Open Settings → Twin seed live readiness (offline-honest)"
          >
            Settings · twin seed readiness
          </a>
          {/* Residual (xa): L3 twin live-seed checklist section deep-link. */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l3-twin"
            data-testid="twin-notes-dual-gate-checklist-link"
            title="Dual-gate L3 twin live seed checklist (prep only · offline default)"
          >
            Dual-gate L3 twin checklist
          </a>
        </p>
        {/* Residual (kr): depth posture when host passes researchTier. */}
        {normalizedResearchTier ? (
          <p
            className="meta font-mono text-[11px]"
            data-testid="twin-notes-research-tier"
            data-research-tier={normalizedResearchTier}
            role="status"
          >
            Research tier: <strong>{normalizedResearchTier}</strong>
            {normalizedResearchTier === "wrestle"
              ? " · multi-minute long-horizon depth"
              : normalizedResearchTier === "fast"
                ? " · flash / distill depth"
                : " · deep / synthesize depth"}
          </p>
        ) : null}
        {/* Residual (nc): model + budget + depth co-display on note-taker. */}
        <div data-testid="twin-notes-driver-badge-mount">
          <DecisionTreeDriverBadge
            researchTier={
              (chaseTier ||
                normalizedResearchTier ||
                undefined) as ResearchLaunchTier | undefined
            }
            promptText={chasePromptPreview || undefined}
          />
        </div>
      </header>
      <div className="controls" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <select
          data-testid="twin-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as "insight" | "question")}
          disabled={busy}
        >
          <option value="insight">insight</option>
          <option value="question">question</option>
        </select>
        <input
          type="text"
          data-testid="twin-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Insight or question…"
          disabled={busy}
          style={{ minWidth: "12rem", flex: 1 }}
        />
        <button
          type="button"
          data-testid="twin-record"
          onClick={() => void record()}
          disabled={busy || !text.trim()}
        >
          Record
        </button>
        <button
          type="button"
          data-testid="twin-refresh"
          onClick={() => void load()}
          disabled={busy}
        >
          Refresh
        </button>
        {/* Residual (mq): selective promote by twin kind. */}
        <label className="flex items-center gap-1 text-[11px] font-mono">
          <span className="opacity-70">Promote</span>
          <select
            data-testid="twin-promote-kinds"
            value={promoteKinds}
            onChange={(e) =>
              setPromoteKinds(
                e.target.value as "all" | "insight" | "question",
              )
            }
            disabled={busy}
            aria-label="Twin kinds to promote"
          >
            <option value="all">all kinds</option>
            <option value="insight">insights only</option>
            <option value="question">questions only</option>
          </select>
        </label>
        <button
          type="button"
          data-testid="twin-promote-context"
          onClick={() => void promote()}
          disabled={busy}
          title="Promote twins into research context units (selective kinds)"
        >
          Promote to context
        </button>
        {/* Residual (ms): one-click promote of currently visible kind filter. */}
        <button
          type="button"
          data-testid="twin-promote-visible"
          onClick={() => promoteVisible()}
          disabled={busy}
          title="Promote only the twin kinds currently shown in the list filter"
        >
          Promote visible
          {listFilter !== "all" ? ` (${listFilter})` : ""}
        </button>
        {/* Residual (mx): multi-select promote. */}
        <button
          type="button"
          data-testid="twin-select-all-visible"
          onClick={() => selectAllVisible()}
          disabled={busy || visibleNotes.length === 0}
          title="Select all notes currently shown in the list filter"
        >
          Select visible
        </button>
        {/* Residual (nd): one-click select by kind for chase/promote. */}
        <button
          type="button"
          data-testid="twin-select-questions"
          onClick={() => selectByKind("question")}
          disabled={
            busy ||
            !(twins?.notes || []).some((n) => n.kind === "question")
          }
          title="Select all question twins for chase/promote"
        >
          Select questions
        </button>
        <button
          type="button"
          data-testid="twin-select-insights"
          onClick={() => selectByKind("insight")}
          disabled={
            busy || !(twins?.notes || []).some((n) => n.kind === "insight")
          }
          title="Select all insight twins for promote/merge"
        >
          Select insights
        </button>
        <button
          type="button"
          data-testid="twin-invert-selection"
          onClick={() => invertVisibleSelection()}
          disabled={busy || visibleNotes.length === 0}
          title="Invert multi-select over currently visible twin notes"
        >
          Invert visible
        </button>
        <button
          type="button"
          data-testid="twin-clear-selection"
          onClick={() => clearNoteSelection()}
          disabled={busy || selectedNoteIds.size === 0}
        >
          Clear selection
        </button>
        <button
          type="button"
          data-testid="twin-promote-selected"
          onClick={() => promoteSelected()}
          disabled={busy || selectedNoteIds.size === 0}
          title="Promote only multi-selected twin note_ids"
        >
          Promote selected ({selectedNoteIds.size})
        </button>
        {/* Residual (mz): chase multi-selected twins as floating deep research. */}
        <button
          type="button"
          data-testid="twin-chase-selected"
          onClick={() => void chaseSelected("floating")}
          disabled={
            busy ||
            selectedNoteIds.size === 0 ||
            (chaseBudgetWarn && !chaseForceBudget)
          }
          title="Spin floating deep research from multi-selected twin notes (questions preferred)"
        >
          Chase selected ({selectedNoteIds.size})
        </button>
        <button
          type="button"
          data-testid="twin-chase-selected-full"
          onClick={() => void chaseSelected("full")}
          disabled={
            busy ||
            selectedNoteIds.size === 0 ||
            (chaseBudgetWarn && !chaseForceBudget)
          }
          title="Spin full working-region deep research from multi-selected twin notes"
        >
          Chase full
        </button>
        {/* Residual (pn/ps): open multi-selected twins as HTML draft window. */}
        <button
          type="button"
          data-testid="twin-draft-selected-html"
          onClick={() => openTwinDraft("floating")}
          disabled={busy || selectedNoteIds.size === 0}
          title="Open multi-selected twin notes as HTML draft window (combine before promote)"
        >
          Draft HTML ({selectedNoteIds.size})
        </button>
        <button
          type="button"
          data-testid="twin-draft-selected-html-full"
          onClick={() => openTwinDraft("full")}
          disabled={busy || selectedNoteIds.size === 0}
          title="Open multi-selected twin draft as full working-region HTML window"
        >
          Draft full
        </button>
        {/* Residual (px/qb): N merge assets → load twins → merge draft. */}
        <div
          className="w-full space-y-2 border rounded p-3 my-1"
          data-testid="twin-cross-asset-merge"
          data-view-format="html"
          data-merge-asset-id={mergeAssetId ?? ""}
          data-merge-asset-count={String(mergeBuckets.length)}
          data-merge-note-count={String(
            mergeBuckets.reduce((n, b) => n + (b.twins.note_count ?? 0), 0),
          )}
          data-merge-selected-count={String(mergeSelectedNoteIds.size)}
        >
          <p className="font-mono text-[11px] opacity-90">
            Cross-asset merge (FUTURE-AGENT V1/qb) — load one or more asset_ids,
            select notes on primary + merge assets, open combined HTML draft
            (propose-only · N&gt;2 accumulates).
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="font-mono text-[11px]" htmlFor="twin-merge-asset-id">
              Merge asset_id
            </label>
            <input
              id="twin-merge-asset-id"
              type="text"
              data-testid="twin-merge-asset-id"
              value={mergeAssetIdInput}
              onChange={(e) => setMergeAssetIdInput(e.target.value)}
              placeholder="other-asset-id"
              disabled={busy}
              className="font-mono text-[11px] min-w-[12rem]"
            />
            <button
              type="button"
              data-testid="twin-merge-asset-load"
              onClick={() => void loadMergeAsset()}
              disabled={busy || !mergeAssetIdInput.trim()}
              title="Fetch twin notes for merge asset_id (accumulates; must differ from current)"
            >
              {mergeBuckets.length > 0 ? "Add merge asset" : "Load merge asset"}
            </button>
            <button
              type="button"
              data-testid="twin-merge-draft-html"
              onClick={() => openTwinDraft("floating", { crossAsset: true })}
              disabled={
                busy ||
                mergeBuckets.length === 0 ||
                selectedNoteIds.size === 0 ||
                mergeSelectedNoteIds.size === 0
              }
              title="Merge selected primary + all merge-asset twins → HTML draft window"
            >
              Merge draft HTML
            </button>
            <button
              type="button"
              data-testid="twin-merge-draft-html-full"
              onClick={() => openTwinDraft("full", { crossAsset: true })}
              disabled={
                busy ||
                mergeBuckets.length === 0 ||
                selectedNoteIds.size === 0 ||
                mergeSelectedNoteIds.size === 0
              }
              title="Merge selected twins → full working-region HTML draft"
            >
              Merge draft full
            </button>
          </div>
          {mergeLoadStatus ? (
            <p
              className="font-mono text-[11px] opacity-80"
              data-testid="twin-merge-load-status"
              role="status"
            >
              {mergeLoadStatus}
            </p>
          ) : null}
          {mergeBuckets.length > 0 ? (
            <div
              className="space-y-2"
              data-testid="twin-merge-notes-list"
              data-asset-id={mergeAssetId ?? ""}
              data-merge-asset-count={String(mergeBuckets.length)}
            >
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  data-testid="twin-merge-select-all"
                  onClick={() => selectAllMergeNotes()}
                  disabled={busy}
                >
                  Select all merge notes
                </button>
                <button
                  type="button"
                  data-testid="twin-merge-clear-selection"
                  onClick={() => clearMergeNoteSelection()}
                  disabled={busy || mergeSelectedNoteIds.size === 0}
                >
                  Clear merge selection
                </button>
              </div>
              {mergeBuckets.map((bucket) => {
                const sel = new Set(bucket.selectedNoteIds);
                return (
                  <div
                    key={bucket.asset_id}
                    className="border rounded p-2 space-y-1"
                    data-testid={`twin-merge-bucket-${bucket.asset_id}`}
                    data-asset-id={bucket.asset_id}
                    data-selected-count={String(bucket.selectedNoteIds.length)}
                  >
                    <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
                      <strong>Merge asset:</strong>{" "}
                      <code>{bucket.asset_id}</code>
                      <button
                        type="button"
                        data-testid={`twin-merge-remove-${bucket.asset_id}`}
                        onClick={() => removeMergeBucket(bucket.asset_id)}
                        disabled={busy}
                        title="Remove this merge asset from the combine set"
                      >
                        Remove
                      </button>
                    </div>
                    <ul className="space-y-1 list-none p-0 m-0">
                      {(bucket.twins.notes || []).map((n) => {
                        const nid = String(n.note_id || "").trim();
                        if (!nid) return null;
                        const checked = sel.has(nid);
                        return (
                          <li key={nid} className="font-mono text-[11px]">
                            <label className="flex items-start gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                data-testid={`twin-merge-select-${nid}`}
                                data-selected={checked ? "1" : "0"}
                                data-merge-asset-id={bucket.asset_id}
                                checked={checked}
                                onChange={() =>
                                  toggleMergeNoteSelection(nid, bucket.asset_id)
                                }
                                disabled={busy}
                              />
                              <span>
                                <strong>{n.kind}</strong>: {n.text}
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
        {draftMetrics ? (
          <div
            className="w-full space-y-1 font-mono text-[11px] opacity-80"
            data-testid="twin-draft-metrics"
            data-note-count={String(draftMetrics.note_count)}
            data-note-ids={
              draftMetrics.note_ids.length <= 6
                ? draftMetrics.note_ids.join(",")
                : `${draftMetrics.note_ids.slice(0, 6).join(",")},+${draftMetrics.note_ids.length - 6}`
            }
            data-window-id={draftMetrics.window_id ?? ""}
            data-write-seed-key={draftMetrics.write_seed_key ?? ""}
            data-has-write-href={draftMetrics.write_href ? "1" : "0"}
            data-window-mode={
              (draftMetrics.window_id || "").includes(":full")
                ? "full"
                : "floating"
            }
            data-view-format="html"
            data-source={
              draftMetrics.merge_source || "twin_draft_selected"
            }
            // Residual (adi): depth posture on recursive note-taker draft audit.
            data-research-tier={draftMetrics.research_tier || ""}
            data-merge-assets={
              draftMetrics.merge_asset_ids?.join("|") ?? ""
            }
            role="status"
          >
            <p>
              Twin draft · notes={draftMetrics.note_count} · note_ids=
              {draftMetrics.note_ids.length <= 6
                ? draftMetrics.note_ids.join(",")
                : `${draftMetrics.note_ids.slice(0, 6).join(",")},+${draftMetrics.note_ids.length - 6}`}{" "}
              · window=
              {draftMetrics.window_id ?? "(none)"} · {draftMetrics.title}
              {draftMetrics.research_tier ? (
                <> · tier={draftMetrics.research_tier}</>
              ) : null}
              {draftMetrics.merge_asset_ids?.length ? (
                <> · merge={draftMetrics.merge_asset_ids.join("+")}</>
              ) : null}
            </p>
            {draftMetrics.write_href ? (
              <a
                href={draftMetrics.write_href}
                data-testid="twin-draft-open-write"
                data-view-format="html"
                // Residual (acq): body honesty on twin draft twin_seed (parity acp).
                data-write-seed-has-body={String(
                  Boolean(draftMetrics.write_seed_has_body),
                )}
                className="underline opacity-90 hover:opacity-100"
                title="Open Write with twin draft as brainstorm seed (sessionStorage; no server invent)"
              >
                Open Write (twin seed)
              </a>
            ) : null}
          </div>
        ) : null}
      </div>
      {/* Residual (na): budget projection soft-gate when multi-select is active. */}
      {selectedNoteIds.size > 0 ? (
        <div
          className="space-y-2 border rounded p-3 my-2"
          data-testid="twin-chase-budget-mount"
          data-view-format="html"
          data-research-tier={chaseTier}
          data-selected-count={String(selectedNoteIds.size)}
          data-budget-warn={String(chaseBudgetWarn)}
          data-force-budget={String(chaseForceBudget)}
        >
          <ResearchLaunchBudgetPanel
            promptText={chasePromptPreview || "twin chase"}
            researchTier={chaseTier}
            allowTierPick
            onResearchTierChange={setChaseTier}
            onProjectionChange={(p: ResearchLaunchBudgetProjection) => {
              setChaseBudgetWarn(p.wouldExceedBudget === true);
            }}
          />
          {chaseBudgetWarn ? (
            <label className="flex items-center gap-2 text-[11px] font-mono">
              <input
                type="checkbox"
                data-testid="twin-chase-force-budget"
                checked={chaseForceBudget}
                onChange={(e) => setChaseForceBudget(e.target.checked)}
              />
              Force chase despite budget projection
            </label>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {seedStatus ? (
        <p
          className="meta font-mono text-[11px]"
          data-testid="twin-seed-status"
          data-offline-honest={
            seedHonesty ? String(seedHonesty.offlineHonest) : undefined
          }
          data-live-seed={
            seedHonesty ? String(seedHonesty.liveSeed) : undefined
          }
          data-seeded={
            seedHonesty ? String(seedHonesty.seeded) : undefined
          }
          data-seed-source={seedHonesty?.seedSource}
          data-seed-skipped={seedHonesty?.seedSkipped ?? undefined}
          data-force-offline="true"
          role="status"
        >
          {seedStatus}
        </p>
      ) : null}
      {promoteStatus ? (
        <p
          className="meta font-mono text-[11px]"
          data-testid="twin-promote-status"
          role="status"
        >
          {promoteStatus}
        </p>
      ) : null}
      {chaseStatus ? (
        <p
          className="meta font-mono text-[11px]"
          data-testid="twin-chase-status"
          data-selected-count={String(selectedNoteIds.size)}
          role="status"
        >
          {chaseStatus}
        </p>
      ) : null}
      {chaseMetrics ? (
        <div
          data-testid="twin-chase-metrics"
          data-spawn-id={chaseMetrics.spawnId}
          data-session-id={chaseMetrics.sessionId}
          data-model-id={chaseMetrics.modelId ?? "none"}
          data-research-tier={chaseMetrics.researchTier}
          data-view-mode={chaseMetrics.viewMode}
          data-note-id-count={String(chaseMetrics.noteIdCount)}
          data-note-ids={chaseMetrics.noteIds.join(",")}
          data-force-budget={String(chaseMetrics.forceBudget)}
          data-view-format={chaseMetrics.viewFormat}
          data-usage-source={chaseMetrics.usageSource ?? ""}
          data-usage-task-class={chaseMetrics.usageTaskClass ?? ""}
          data-collective-recent="true"
          className="font-mono text-[11px] opacity-80"
          role="status"
        >
          Twin chase metrics · spawn={chaseMetrics.spawnId} · model=
          {chaseMetrics.modelId ?? "none"} · tier={chaseMetrics.researchTier} ·
          mode={chaseMetrics.viewMode} · notes={chaseMetrics.noteIdCount}
          {chaseMetrics.noteIds.length > 0
            ? ` · note_ids=${chaseMetrics.noteIds.join(",")}`
            : ""}
          {chaseMetrics.usageSource
            ? ` · bench=${chaseMetrics.usageSource}/${chaseMetrics.usageTaskClass ?? "?"}`
            : ""}
          {" · collective=recent_ring"}
          {chaseMetrics.forceBudget ? " · force_budget" : ""}
        </div>
      ) : null}

      {twins ? (
        <div data-testid="twin-notes-summary" className="font-mono text-sm">
          {/* Residual (fk): machine-readable recursive note-taker metrics. */}
          <div
            data-testid="twin-notes-metrics"
            data-note-count={String(twins.note_count ?? 0)}
            data-insight-count={String(twins.insight_count ?? 0)}
            data-question-count={String(twins.question_count ?? 0)}
            data-list-filter={listFilter}
            data-visible-count={String(visibleNotes.length)}
            data-research-tier={normalizedResearchTier}
            data-view-format="html"
            role="status"
          >
            Recursive note-taker · notes={twins.note_count ?? 0} · insights=
            {twins.insight_count ?? 0} · questions={twins.question_count ?? 0}
            {normalizedResearchTier ? ` · tier=${normalizedResearchTier}` : ""}
            {listFilter !== "all"
              ? ` · showing ${listFilter}=${visibleNotes.length}`
              : ""}
          </div>
          {/* Residual (mr): browse filter before selective promote. */}
          <label className="flex items-center gap-1 text-[11px] font-mono">
            <span className="opacity-70">Show</span>
            <select
              data-testid="twin-list-filter"
              value={listFilter}
              onChange={(e) =>
                setListFilter(
                  e.target.value as "all" | "insight" | "question",
                )
              }
              disabled={busy}
              aria-label="Filter twin notes by kind"
            >
              <option value="all">all notes</option>
              <option value="insight">insights only</option>
              <option value="question">questions only</option>
            </select>
          </label>
          <p>
            notes={twins.note_count} · insights={twins.insight_count} · questions=
            {twins.question_count}
            {listFilter !== "all"
              ? ` · visible=${visibleNotes.length}`
              : ""}
          </p>
          <ul data-testid="twin-notes-list">
            {visibleNotes.map((n) => (
              <li
                key={n.note_id}
                data-kind={n.kind}
                data-note-id={n.note_id}
                data-selected={String(selectedNoteIds.has(n.note_id))}
              >
                {/* Residual (mx): multi-select checkbox per twin note. */}
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    data-testid={`twin-select-${n.note_id}`}
                    checked={selectedNoteIds.has(n.note_id)}
                    onChange={() => toggleNoteSelected(n.note_id)}
                    disabled={busy}
                    aria-label={`Select twin note ${n.note_id}`}
                  />
                  <span>
                    <strong>[{n.kind}]</strong> {n.text}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <p
            className="text-[11px] font-mono opacity-70"
            data-testid="twin-selection-count"
            data-selected-count={String(selectedNoteIds.size)}
            role="status"
          >
            Selected notes: {selectedNoteIds.size}
          </p>
          {twins.notes.length > 0 && visibleNotes.length === 0 ? (
            <p
              className="text-[11px] font-mono opacity-70"
              data-testid="twin-list-filter-empty"
            >
              No {listFilter} notes in this twin substrate.
            </p>
          ) : null}
          {twins.html ? (
            <div
              data-testid="twin-notes-html"
              dangerouslySetInnerHTML={{ __html: twins.html }}
            />
          ) : null}
        </div>
      ) : null}
      {promoted ? (
        <div
          data-testid="twin-promote-result"
          data-view-format="html"
          className="font-mono text-sm"
        >
          {/* Residual (hi/my/adl): machine-readable promote→context metrics + depth. */}
          <div
            data-testid="twin-promote-metrics"
            data-promoted-count={String(promoted.promoted_count ?? 0)}
            data-context-unit-count={String(promoted.context_unit_count ?? 0)}
            data-promote-kinds={promoteKinds}
            data-selected-count={String(selectedNoteIds.size)}
            data-promoted-note-ids={
              Array.isArray(promoted.note_ids) && promoted.note_ids.length > 0
                ? promoted.note_ids.join(",")
                : ""
            }
            data-promoted-note-id-count={String(
              Array.isArray(promoted.note_ids) ? promoted.note_ids.length : 0,
            )}
            data-view-format="html"
            // Residual (adl): depth posture on promote→context path (parity adi draft).
            data-research-tier={normalizedResearchTier || ""}
            data-product-panel={
              promoted.product_panel ?? "twin_promote_context"
            }
            data-source={promoted.source ?? "engagement_spine.twin_promote"}
            role="status"
          >
            Twin promote → context · promoted={promoted.promoted_count ?? 0} ·
            context_units={promoted.context_unit_count ?? 0}
            {promoteKinds !== "all" ? ` · kinds=${promoteKinds}` : ""}
            {Array.isArray(promoted.note_ids) && promoted.note_ids.length > 0
              ? ` · note_ids=${promoted.note_ids.length}`
              : ""}
            {normalizedResearchTier
              ? ` · tier=${normalizedResearchTier}`
              : ""}
          </div>
          <p>
            promoted={promoted.promoted_count} · context_units=
            {promoted.context_unit_count}
          </p>
          <ul data-testid="twin-promote-units">
            {promoted.context_units.map((u) => (
              <li key={u.unit_id}>
                <strong>[{u.kind}]</strong> {u.text}
              </li>
            ))}
          </ul>
          {/* Residual (rr/acq): promote → Write twin_seed + body honesty. */}
          {(() => {
            const href = buildTwinPromoteWriteHref({
              assetId: promoted.asset_id || assetId,
              query: promoted.query,
              contextUnits: promoted.context_units,
              noteIds: promoted.note_ids,
              html: promoted.html,
              promotedCount: promoted.promoted_count,
            });
            const unitBody = (promoted.context_units || []).some((u) =>
              Boolean(String(u?.text || "").trim()),
            );
            const hasBody = Boolean(
              unitBody || plainTextFromHtml(promoted.html || "").trim(),
            );
            return href ? (
              <p className="meta font-mono text-[11px]">
                <a
                  href={href}
                  data-testid="twin-promote-open-write"
                  data-view-format="html"
                  data-has-twin-seed="1"
                  data-promoted-count={String(promoted.promoted_count ?? 0)}
                  // Residual (acq): body honesty when units or HTML body non-empty.
                  data-write-seed-has-body={String(hasBody)}
                  className="underline opacity-90 hover:opacity-100"
                  title="Open Write with promoted twin context units as twin_seed (sessionStorage; no invented document_id)"
                >
                  Open Write (promoted twins)
                </a>
              </p>
            ) : null;
          })()}
          {promoted.notes?.map((n) => (
            <p key={n} className="meta">
              {n}
            </p>
          ))}
          {promoted.html ? (
            <div
              data-testid="twin-promote-html"
              dangerouslySetInnerHTML={{ __html: promoted.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default TwinNotesPanel;
