/**
 * ResearchContextPanel — workstation chrome for twin + source-ref context.
 *
 * Loads a ResearchContextPack from /engagement/research-context and renders
 * the prompt block for injection into the next deep-research turn.
 * HTML-first stance: this panel never offers PDF export.
 *
 * Residual (ff): recursive note-taker metrics strip — insight/question/other
 * twin breakdown so operators see the twin substrate that feeds prompts.
 * Residual (kd): evidence pack surfaces spawn research_tier (depth posture).
 * Residual (kl): research context pack surfaces spawn research_tier chrome.
 * Residual (mu): dual-gate L1–L4 checklist deep-link for hydrate L1/L2 prep.
 * Residual (qq): DecisionTreeDriverBadge + promptText from prompt_block / query
 *     so recursive context pack cost foresight sits next to the substrate.
 * Residual (rb): Open Write twin_seed from evidence pack (insights/questions/refs).
 * Residual (rf): Open Write twin_seed from intelligent context search hits.
 * Residual (rh): Open Write twin_seed from single hydrate-ref result.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  attachSourceRefs,
  fetchEvidencePack,
  fetchResearchContext,
  hydratePublicationRef,
  promoteTwinsToContext,
  searchEngagementContext,
  type ContextSearchResponse,
  type EvidencePackResponse,
  type HydrateRefResponse,
  type ResearchContextResponse,
  type TwinPromoteContextResponse,
} from "../../api/engagement";
import { detectSourceKindClient } from "../../workspace/researchContextPack";
import {
  buildContextSearchWriteHref,
  buildEvidencePackWriteHref,
  buildPublicationHydrateWriteHref,
} from "../../workspace/twinWriteSeed";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

/** Pure twin-kind metrics for recursive note-taker substrate (residual ff). */
export function twinNoteMetrics(
  pack: Pick<ResearchContextResponse, "twin_units" | "twin_count"> | null,
): {
  total: number;
  insights: number;
  questions: number;
  other: number;
} {
  const units = pack?.twin_units ?? [];
  let insights = 0;
  let questions = 0;
  let other = 0;
  for (const u of units) {
    const k = (u.kind || "").toLowerCase();
    if (k === "insight") insights += 1;
    else if (k === "question") questions += 1;
    else other += 1;
  }
  const fromUnits = units.length;
  const total =
    pack?.twin_count != null && pack.twin_count >= fromUnits
      ? pack.twin_count
      : fromUnits;
  return { total, insights, questions, other };
}

export type ResearchContextPanelProps = {
  assetId: string;
  spawnId?: string | null;
  /** Optional controlled initial query filter */
  initialQuery?: string;
  /**
   * Residual (co): auto-load research context + evidence pack on mount
   * (competitive citation-trust surface without extra clicks).
   */
  autoLoad?: boolean;
};

export function ResearchContextPanel({
  assetId,
  spawnId = null,
  initialQuery = "",
  autoLoad = false,
}: ResearchContextPanelProps) {
  const [query, setQuery] = useState(initialQuery);
  const [refInput, setRefInput] = useState("");
  const [pack, setPack] = useState<ResearchContextResponse | null>(null);
  const [evidence, setEvidence] = useState<EvidencePackResponse | null>(null);
  const [hydrated, setHydrated] = useState<HydrateRefResponse | null>(null);
  const [searchHits, setSearchHits] = useState<ContextSearchResponse | null>(
    null,
  );
  const [flywheel, setFlywheel] = useState<TwinPromoteContextResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Residual (ff): insight/question breakdown of twin note substrate.
  const twinMetrics = useMemo(() => twinNoteMetrics(pack), [pack]);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const ctx = await fetchResearchContext({
        asset_id: assetId,
        spawn_id: spawnId,
        query: query.trim() || null,
      });
      if (ctx.view_format !== "html") {
        throw new Error("research context view_format must be html");
      }
      setPack(ctx);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId, spawnId, query]);

  const loadEvidence = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const packEv = await fetchEvidencePack({
        asset_id: assetId,
        spawn_id: spawnId,
        include_html: true,
      });
      if (packEv.view_format !== "html") {
        throw new Error("evidence pack view_format must be html");
      }
      setEvidence(packEv);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId, spawnId]);

  useEffect(() => {
    if (!autoLoad || !assetId.trim()) return;
    void load();
    void loadEvidence();
    // Intentionally once per asset/spawn identity when autoLoad is on.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- residual (co) mount-once
  }, [autoLoad, assetId, spawnId]);

  const attach = useCallback(async () => {
    if (!spawnId || !refInput.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await attachSourceRefs(spawnId, [refInput.trim()]);
      setRefInput("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }, [spawnId, refInput, load]);

  const hydrate = useCallback(async () => {
    if (!refInput.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const asset = await hydratePublicationRef({
        reference: refInput.trim(),
        include_html: true,
        attach_spawn_id: spawnId,
      });
      if (asset.view_format !== "html") {
        throw new Error("hydrate view_format must be html");
      }
      setHydrated(asset);
      if (spawnId) await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [refInput, spawnId, load]);

  const searchContext = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setError("Enter a query filter to search twins/refs");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const hits = await searchEngagementContext({
        query: q,
        asset_id: assetId,
        spawn_id: spawnId,
        include_html: true,
      });
      if (hits.view_format !== "html") {
        throw new Error("context search view_format must be html");
      }
      setSearchHits(hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [query, assetId, spawnId]);

  /** Residual (bm): promote twins → load research context pack in one click. */
  const runContextFlywheel = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const promoted = await promoteTwinsToContext({
        asset_id: assetId,
        query: query.trim() || null,
        include_html: true,
      });
      if (promoted.view_format !== "html") {
        throw new Error("promote view_format must be html");
      }
      setFlywheel(promoted);
      const ctx = await fetchResearchContext({
        asset_id: assetId,
        spawn_id: spawnId,
        query: query.trim() || null,
        include_twin_promote: true,
      });
      if (ctx.view_format !== "html") {
        throw new Error("research context view_format must be html");
      }
      setPack(ctx);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [assetId, spawnId, query]);

  return (
    <section
      className="research-context-panel"
      data-view-format="html"
      data-testid="research-context-panel"
      aria-label="Research context"
    >
      <header>
        <h2>Research context</h2>
        {/* Residual (ie/mu): Settings + dual-gate checklist (L1/L2 hydrate prep). */}
        <p className="meta font-mono text-[11px] space-x-3">
          <a
            href="/settings"
            data-testid="research-context-settings-link"
            title="Open Settings → Publication hydrate readiness"
          >
            Settings · hydrate readiness
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
            data-testid="research-context-dual-gate-checklist-link"
            title="Dual-gate L1–L4 checklist (arxiv/substack hydrate prep; offline default)"
          >
            Dual-gate L1–L4 checklist
          </a>
        </p>
        <p className="meta">
          asset <code>{assetId}</code>
          {spawnId ? (
            <>
              {" "}
              · spawn <code>{spawnId}</code>
            </>
          ) : null}
        </p>
        {/* Residual (qq): model + budget + depth co-display over recursive context. */}
        <div
          className="mt-1"
          data-testid="research-context-driver-badge-mount"
          data-view-format="html"
          data-research-tier={
            (pack?.research_tier || "").trim().toLowerCase() || ""
          }
        >
          <DecisionTreeDriverBadge
            researchTier={
              ((pack?.research_tier || "").trim().toLowerCase() ||
                undefined) as "fast" | "deep" | "wrestle" | undefined
            }
            promptText={
              (pack?.prompt_block || "").trim() ||
              (query.trim()
                ? `research context query · ${query.trim()}`
                : `research context · ${assetId}`)
            }
          />
        </div>
      </header>

      <div className="controls">
        <label>
          Query filter
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter twins / refs"
            disabled={busy}
          />
        </label>
        <button
          type="button"
          data-testid="load-research-context"
          onClick={() => void load()}
          disabled={busy}
        >
          {busy ? "Loading…" : "Load context"}
        </button>
        <button
          type="button"
          data-testid="load-evidence-pack"
          onClick={() => void loadEvidence()}
          disabled={busy}
        >
          {busy ? "Loading…" : "Load evidence pack"}
        </button>
        <button
          type="button"
          data-testid="context-search"
          onClick={() => void searchContext()}
          disabled={busy || !query.trim()}
        >
          Search twins/refs
        </button>
        <button
          type="button"
          data-testid="context-flywheel"
          onClick={() => void runContextFlywheel()}
          disabled={busy}
          title="Promote twins then load research context pack"
        >
          Promote twins → load context
        </button>
      </div>

      <div className="attach-refs">
        <label>
          Source (arxiv / substack / url)
          <input
            type="text"
            value={refInput}
            onChange={(e) => setRefInput(e.target.value)}
            placeholder="https://arxiv.org/abs/… or 1706.03762"
            disabled={busy}
          />
        </label>
        {refInput.trim() ? (
          <span className="kind-hint" data-kind={detectSourceKindClient(refInput)}>
            kind: {detectSourceKindClient(refInput)}
          </span>
        ) : null}
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {spawnId ? (
            <button
              type="button"
              onClick={() => void attach()}
              disabled={busy || !refInput.trim()}
            >
              Attach ref
            </button>
          ) : null}
          <button
            type="button"
            data-testid="hydrate-publication-ref"
            onClick={() => void hydrate()}
            disabled={busy || !refInput.trim()}
          >
            Hydrate HTML asset
          </button>
        </div>
      </div>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {pack ? (
        <div
          className="pack"
          data-testid="research-context-pack"
          data-view-format="html"
          data-research-tier={
            (pack.research_tier || "").trim().toLowerCase() || ""
          }
        >
          <p className="counts">
            twins={pack.twin_count ?? pack.twin_units?.length ?? 0} · refs=
            {pack.ref_count ?? pack.source_references?.length ?? 0}
            {pack.research_tier ? ` · tier=${pack.research_tier}` : ""}
          </p>
          {/* Residual (ff): recursive note-taker metrics (insight/question twin substrate). */}
          <div
            className="meta font-mono text-[11px]"
            data-testid="research-context-twin-metrics"
            data-twin-total={String(twinMetrics.total)}
            data-twin-insights={String(twinMetrics.insights)}
            data-twin-questions={String(twinMetrics.questions)}
            data-twin-other={String(twinMetrics.other)}
            data-research-tier={
              (pack.research_tier || "").trim().toLowerCase() || ""
            }
            role="status"
          >
            Recursive note-taker · insights={twinMetrics.insights} · questions=
            {twinMetrics.questions}
            {twinMetrics.other > 0 ? ` · other=${twinMetrics.other}` : ""} ·
            total={twinMetrics.total}
            {pack.research_tier ? ` · tier=${pack.research_tier}` : ""}
          </div>
          {/* Residual (kl): spawn research_tier depth posture on context pack. */}
          {pack.research_tier ? (
            <p
              className="meta font-mono text-[11px]"
              data-testid="research-context-research-tier"
              data-research-tier={String(pack.research_tier)
                .trim()
                .toLowerCase()}
              role="status"
            >
              Research tier: <strong>{pack.research_tier}</strong>
              {String(pack.research_tier).toLowerCase() === "wrestle"
                ? " · multi-minute long-horizon depth"
                : String(pack.research_tier).toLowerCase() === "fast"
                  ? " · flash / distill depth"
                  : " · deep / synthesize depth"}
            </p>
          ) : null}
          <ul className="twins">
            {(pack.twin_units ?? []).map((u) => (
              <li key={u.unit_id}>
                <strong>[{u.kind}]</strong> {u.text}
              </li>
            ))}
          </ul>
          <ul className="refs">
            {(pack.source_references ?? []).map((r) => (
              <li key={r.ref_id}>
                <strong>[{r.kind}]</strong> {r.canonical_url || r.raw}
              </li>
            ))}
          </ul>
          <pre className="prompt-block" data-testid="prompt-block">
            {pack.prompt_block}
          </pre>
        </div>
      ) : null}

      {evidence ? (
        <div
          className="evidence-pack"
          data-testid="evidence-pack-result"
          data-view-format="html"
          data-ref-count={String(evidence.ref_count ?? 0)}
          data-research-tier={
            (evidence.research_tier || "").trim().toLowerCase() || ""
          }
          data-citation-trust={
            (evidence.ref_count ?? 0) > 0 ? "grounded" : "ungrounded"
          }
        >
          {/* Residual (hu/kd): machine-readable competitive citation + depth. */}
          <div
            data-testid="evidence-pack-metrics"
            data-insight-count={String(evidence.insight_count ?? 0)}
            data-question-count={String(evidence.question_count ?? 0)}
            data-ref-count={String(evidence.ref_count ?? 0)}
            data-research-tier={
              (evidence.research_tier || "").trim().toLowerCase() || ""
            }
            data-citation-trust={
              (evidence.ref_count ?? 0) > 0 ? "grounded" : "ungrounded"
            }
            data-view-format="html"
            role="status"
          >
            Evidence pack · insights={evidence.insight_count ?? 0} · questions=
            {evidence.question_count ?? 0} · refs={evidence.ref_count ?? 0} ·
            trust=
            {(evidence.ref_count ?? 0) > 0 ? "grounded" : "ungrounded"}
            {evidence.research_tier
              ? ` · tier=${evidence.research_tier}`
              : ""}
          </div>
          <p className="counts">
            evidence · insights={evidence.insight_count} · questions=
            {evidence.question_count} · refs={evidence.ref_count}
          </p>
          {/* Residual (kd): spawn research_tier depth posture (citation trust). */}
          {evidence.research_tier ? (
            <p
              className="meta font-mono text-[11px]"
              data-testid="evidence-research-tier"
              data-research-tier={String(evidence.research_tier)
                .trim()
                .toLowerCase()}
              role="status"
            >
              Research tier: <strong>{evidence.research_tier}</strong>
              {String(evidence.research_tier).toLowerCase() === "wrestle"
                ? " · multi-minute long-horizon depth"
                : String(evidence.research_tier).toLowerCase() === "fast"
                  ? " · flash / distill depth"
                  : " · deep / synthesize depth"}
            </p>
          ) : null}
          {/* Residual (dm): competitive bar — never pretend citations exist. */}
          {(evidence.ref_count ?? 0) === 0 ? (
            <p
              className="meta font-mono text-[11px] text-emperor"
              data-testid="evidence-citation-trust"
              role="status"
            >
              Citation trust: ungrounded — attach arxiv/substack/URL refs or
              seed twins before treating this pack as competitive-grade
              synthesis.
            </p>
          ) : (
            <p
              className="meta font-mono text-[11px]"
              data-testid="evidence-citation-trust"
              role="status"
            >
              Citation trust: grounded · {evidence.ref_count} source ref(s)
            </p>
          )}
          {/* Residual (rb): evidence pack → Write twin_seed handoff. */}
          {(() => {
            const href = buildEvidencePackWriteHref({
              assetId: evidence.asset_id || assetId,
              spawnId: evidence.spawn_id || spawnId,
              insights: evidence.insights,
              questions: evidence.questions,
              sourceReferences: evidence.source_references,
              html: evidence.html,
              researchTier: evidence.research_tier,
            });
            return href ? (
              <p className="meta font-mono text-[11px]">
                <a
                  href={href}
                  data-testid="evidence-pack-open-write"
                  data-view-format="html"
                  data-has-twin-seed="1"
                  data-ref-count={String(evidence.ref_count ?? 0)}
                  className="underline opacity-90 hover:opacity-100"
                  title="Open Write with evidence pack as twin_seed (insights/questions/refs; no invented document_id)"
                >
                  Open Write (evidence pack)
                </a>
              </p>
            ) : null;
          })()}
          {evidence.html ? (
            <div
              className="evidence-html"
              data-testid="evidence-pack-html"
              dangerouslySetInnerHTML={{ __html: evidence.html }}
            />
          ) : null}
        </div>
      ) : null}

      {hydrated ? (
        <div
          className="hydrate-result"
          data-testid="hydrate-ref-result"
          data-view-format="html"
          data-fetched={String(Boolean(hydrated.fetched))}
          data-offline-honest={
            hydrated.offline_honest !== false && !hydrated.fetched
              ? "true"
              : "false"
          }
        >
          <p>
            hydrated asset <code>{hydrated.asset_id}</code> · fetched=
            {String(hydrated.fetched)} · {hydrated.title}
          </p>
          {/* Residual (hd): offline-honest identity vs injector body. */}
          <p
            className="meta font-mono text-[11px]"
            data-testid="hydrate-ref-offline-honest"
            role="status"
          >
            {hydrated.offline_honest !== false && !hydrated.fetched
              ? "Hydrate mode: offline-honest identity — no live body; not invented abstract"
              : "Hydrate mode: injector body landed"}
          </p>
          {/* Residual (rh): single hydrate → Write twin_seed. */}
          {(() => {
            const href = buildPublicationHydrateWriteHref({
              spawnId,
              assets: [hydrated],
            });
            return href ? (
              <p className="meta font-mono text-[11px]">
                <a
                  href={href}
                  data-testid="hydrate-ref-open-write"
                  data-view-format="html"
                  data-has-twin-seed="1"
                  data-asset-id={hydrated.asset_id}
                  className="underline opacity-90 hover:opacity-100"
                  title="Open Write with hydrated publication as twin_seed (no invented document_id)"
                >
                  Open Write (hydrated pub)
                </a>
              </p>
            ) : null;
          })()}
          {hydrated.html ? (
            <div
              data-testid="hydrate-ref-html"
              dangerouslySetInnerHTML={{ __html: hydrated.html }}
            />
          ) : null}
        </div>
      ) : null}

      {searchHits ? (
        <div
          className="context-search-result"
          data-testid="context-search-result"
          data-view-format="html"
          data-research-tier={
            (searchHits.research_tier || "").trim().toLowerCase() || ""
          }
        >
          {/* Residual (fi/kg): intelligent search metrics + spawn tier. */}
          <div
            className="meta font-mono text-[11px]"
            data-testid="context-search-metrics"
            data-hit-count={String(searchHits.hit_count ?? 0)}
            data-query={searchHits.query ?? ""}
            data-research-tier={
              (searchHits.research_tier || "").trim().toLowerCase() || ""
            }
            role="status"
          >
            Intelligent search · query=
            <code>{searchHits.query}</code> · hits=
            {searchHits.hit_count ?? 0}
            {searchHits.research_tier
              ? ` · tier=${searchHits.research_tier}`
              : ""}
          </div>
          <p className="counts">
            search “{searchHits.query}” · hits={searchHits.hit_count}
            {searchHits.research_tier ? (
              <>
                {" "}
                · tier=
                <code data-testid="context-search-research-tier">
                  {searchHits.research_tier}
                </code>
              </>
            ) : null}
          </p>
          <ul data-testid="context-search-hits">
            {searchHits.hits.map((h) => (
              <li key={`${h.kind}-${h.id}`}>
                <strong>[{h.kind}]</strong> {h.text}
              </li>
            ))}
          </ul>
          {/* Residual (rf): search hits → Write twin_seed. */}
          {(() => {
            const href = buildContextSearchWriteHref({
              assetId: searchHits.asset_id || assetId,
              query: searchHits.query,
              hits: searchHits.hits,
              html: searchHits.html,
              researchTier: searchHits.research_tier,
            });
            return href ? (
              <p className="meta font-mono text-[11px]">
                <a
                  href={href}
                  data-testid="context-search-open-write"
                  data-view-format="html"
                  data-has-twin-seed="1"
                  data-hit-count={String(searchHits.hit_count ?? 0)}
                  className="underline opacity-90 hover:opacity-100"
                  title="Open Write with context search hits as twin_seed (no invented document_id)"
                >
                  Open Write (search hits)
                </a>
              </p>
            ) : null;
          })()}
          {searchHits.html ? (
            <div
              data-testid="context-search-html"
              dangerouslySetInnerHTML={{ __html: searchHits.html }}
            />
          ) : null}
        </div>
      ) : null}

      {flywheel ? (
        <div
          className="context-flywheel-result"
          data-testid="context-flywheel-result"
          data-view-format="html"
        >
          <p className="counts">
            flywheel promoted={flywheel.promoted_count} · context_units=
            {flywheel.context_unit_count}
          </p>
          {flywheel.html ? (
            <div
              data-testid="context-flywheel-html"
              dangerouslySetInnerHTML={{ __html: flywheel.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default ResearchContextPanel;
