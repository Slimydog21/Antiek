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
 * Residual (nd): one-click select questions|insights into multi-select
 * (chase/promote questions path without manual checkbox grind).
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
  const goal_hint =
    `Twin chase on ${assetId.trim() || "asset"}: ` +
    `${ordered.length} note(s) (questions=${qCount}, insights=${iCount})`;
  return { selection_text, goal_hint, note_ids };
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
    forceBudget: boolean;
    viewFormat: string;
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
        setChaseMetrics({
          spawnId: out.spawn_id,
          sessionId: out.session_id,
          modelId: out.model_id ?? null,
          researchTier: String(out.research_tier || chaseTier),
          viewMode,
          noteIdCount: payload.note_ids.length,
          forceBudget: forced,
          viewFormat: out.view_format,
        });
        const modelLabel = out.model_id?.trim()
          ? ` · model=${out.model_id.trim()}`
          : " · model=none";
        setChaseStatus(
          `chased ${payload.note_ids.length} twin note(s) → spawn=${out.spawn_id} · ` +
            `mode=${viewMode} · tier=${out.research_tier}${modelLabel}` +
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
            href="/settings"
            data-testid="twin-notes-settings-link"
            title="Open Settings → Twin seed live readiness"
          >
            Settings · twin seed readiness
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
            data-testid="twin-notes-dual-gate-checklist-link"
            title="Dual-gate L1–L4 checklist (L3 twin live seed prep; offline default)"
          >
            Dual-gate L1–L4 checklist
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
          data-force-budget={String(chaseMetrics.forceBudget)}
          data-view-format={chaseMetrics.viewFormat}
          className="font-mono text-[11px] opacity-80"
          role="status"
        >
          Twin chase metrics · spawn={chaseMetrics.spawnId} · model=
          {chaseMetrics.modelId ?? "none"} · tier={chaseMetrics.researchTier} ·
          mode={chaseMetrics.viewMode} · notes={chaseMetrics.noteIdCount}
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
          {/* Residual (hi/my): machine-readable promote→context metrics. */}
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
