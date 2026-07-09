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
 * HTML-first; never PDF.
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchTwinNotes,
  promoteTwinsToContext,
  recordTwinNote,
  seedTwinNotes,
  type TwinNotesResponse,
  type TwinPromoteContextResponse,
} from "../../api/engagement";

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

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      let t = await fetchTwinNotes(assetId, { includeHtml: true });
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

  const promote = useCallback(async () => {
    setBusy(true);
    setError(null);
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
        `promoted ${p.promoted_count} twin unit(s) to context`,
      );
      onPromoted?.(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId, onPromoted]);

  return (
    <section
      className="twin-notes-panel"
      data-testid="twin-notes-panel"
      data-view-format="html"
      aria-label="Twin notes"
    >
      <header>
        <h2>Twin notes</h2>
        <p className="meta">
          Recursive note-taker for asset <code>{assetId}</code>
        </p>
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
        <button
          type="button"
          data-testid="twin-promote-context"
          onClick={() => void promote()}
          disabled={busy}
          title="Promote twins into research context units"
        >
          Promote to context
        </button>
      </div>
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
      {twins ? (
        <div data-testid="twin-notes-summary" className="font-mono text-sm">
          {/* Residual (fk): machine-readable recursive note-taker metrics. */}
          <div
            data-testid="twin-notes-metrics"
            data-note-count={String(twins.note_count ?? 0)}
            data-insight-count={String(twins.insight_count ?? 0)}
            data-question-count={String(twins.question_count ?? 0)}
            data-view-format="html"
            role="status"
          >
            Recursive note-taker · notes={twins.note_count ?? 0} · insights=
            {twins.insight_count ?? 0} · questions={twins.question_count ?? 0}
          </div>
          <p>
            notes={twins.note_count} · insights={twins.insight_count} · questions=
            {twins.question_count}
          </p>
          <ul data-testid="twin-notes-list">
            {twins.notes.map((n) => (
              <li key={n.note_id}>
                <strong>[{n.kind}]</strong> {n.text}
              </li>
            ))}
          </ul>
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
          {/* Residual (hi): machine-readable promote→context metrics. */}
          <div
            data-testid="twin-promote-metrics"
            data-promoted-count={String(promoted.promoted_count ?? 0)}
            data-context-unit-count={String(promoted.context_unit_count ?? 0)}
            data-view-format="html"
            data-product-panel={
              promoted.product_panel ?? "twin_promote_context"
            }
            data-source={promoted.source ?? "engagement_spine.twin_promote"}
            role="status"
          >
            Twin promote → context · promoted={promoted.promoted_count ?? 0} ·
            context_units={promoted.context_unit_count ?? 0}
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
