/**
 * PublicationAttachPanel — attach + hydrate arxiv/substack/url onto a spawn.
 *
 * Residual (ck): mid-session knowledge-dense publication attach for deep
 * research windows. Composes attachSourceRefs + hydratePublicationRef.
 * Residual (ed): onAttached notifies parent so research context remounts
 * and source refs appear in the context pack / citation trust surface.
 * Residual (hc): surface offline_honest per hydrated asset so operators
 * never confuse identity-only stubs with live publication bodies.
 * Residual (ia): Settings deep-link for hydrate live-injector readiness (hq).
 * Residual (ko): surface spawn research_tier from attach-refs response.
 * Residual (lz): DecisionTreeDriverBadge — model+budget+depth co-display
 * Residual (qo): DecisionTreeDriverBadge promptText from pub ref list.
 * before/after attach (prop tier preferred; attach response fills when known).
 * Residual (mj): dual-gate L1–L4 checklist deep-link for arxiv/substack
 * live-injector dogfood prep (never enables injectors).
 * Residual (rc): Open Write twin_seed from hydrated publications.
 * Residual (acs): data-write-seed-has-body when any pub body_text/HTML non-empty.
 * Residual (agx): knowledge-dense publication quick-call presets (arxiv / substack
 * / seminal STEM) — one-click insert into the attach input; hydrate still offline-
 * honest until Attach + hydrate (never invents live body).
 * HTML-first; offline hydrate by default.
 */

import { useCallback, useMemo, useState } from "react";
import {
  attachSourceRefs,
  attachSessionReferences,
  hydratePublicationRef,
  type HydrateRefResponse,
} from "../../api/engagement";
import {
  parsePublicationRefs,
} from "../../modes/ResearchWorkstation/publicationRefs";
import { publicationAttachReadiness } from "../../workspace/publicationAttachReadiness";
import {
  buildPublicationHydrateWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";
// Residual (auj): pure catalog lives in workspace — re-export for existing imports.
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../../workspace/knowledgeDensePresets";
export {
  KNOWLEDGE_DENSE_PUBLICATION_PRESETS,
  knowledgeDensePresetById,
  knowledgeDensePresetCount,
  type KnowledgeDensePublicationPreset,
  type KnowledgeDensePublicationKind,
} from "../../workspace/knowledgeDensePresets";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

export type PublicationAttachResult = {
  spawnId: string;
  references: string[];
  hydrated: HydrateRefResponse[];
  view_format: "html";
};

export type PublicationAttachPanelProps = {
  /** Residual (asb): optional until bound — CTA gates on publicationAttachReadiness. */
  spawnId?: string | null;
  sessionId?: string | null;
  /** Residual (ed): fire after successful attach+hydrate (HTML assets only). */
  onAttached?: (result: PublicationAttachResult) => void;
  /**
   * Residual (lz): session/spawn research tier for driver co-display.
   * Prop wins over attach-response tier when both present.
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function PublicationAttachPanel({
  spawnId = "",
  sessionId = null,
  onAttached,
  researchTier: researchTierProp = null,
}: PublicationAttachPanelProps) {
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attached, setAttached] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState<HydrateRefResponse[]>([]);
  const [attachResearchTier, setAttachResearchTier] = useState<string | null>(
    null,
  );

  /** Residual (lz): prop session tier preferred; attach response as fallback. */
  const researchTier = useMemo(() => {
    const fromProp = (researchTierProp || "").trim().toLowerCase();
    if (fromProp) return fromProp;
    return (attachResearchTier || "").trim().toLowerCase() || null;
  }, [researchTierProp, attachResearchTier]);

  // Residual (asb): knowledge-dense attach+hydrate readiness (spawn + refs).
  const attachReadiness = useMemo(
    () =>
      publicationAttachReadiness({
        spawnId,
        refCount: parsePublicationRefs(raw).length,
      }),
    [spawnId, raw],
  );

  const run = useCallback(async () => {
    const sid = String(spawnId || "").trim();
    if (!sid) {
      setError("spawnId is required");
      return;
    }
    const refs = parsePublicationRefs(raw);
    if (refs.length < 1) {
      setError("Add at least one publication ref (one per line)");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const session = String(sessionId || "").trim();
      let assets: HydrateRefResponse[] = [];
      let attachedTier: string | null | undefined;
      if (session) {
        const attach = await attachSessionReferences({
            session_id: session,
            references: refs,
            hydrate: true,
            seed_twins: true,
          });
        if (attach.view_format !== "html") {
          throw new Error("attach view_format must be html");
        }
        assets = attach.hydrated_assets;
        attachedTier = attach.research_tier;
      } else {
        const attach = await attachSourceRefs(sid, refs);
        if (attach.view_format !== "html") {
          throw new Error("attach view_format must be html");
        }
        attachedTier = attach.research_tier;
      }
      setAttached(refs);
      // Residual (ko): reserved spawn research_tier from attach response.
      setAttachResearchTier(
        (attachedTier || "").trim().toLowerCase() || null,
      );
      if (!session) {
        for (const reference of refs) {
          const asset = await hydratePublicationRef({
            reference,
            include_html: true,
            attach_spawn_id: sid,
          });
          if (asset.view_format !== "html") {
            throw new Error(`hydrate view_format must be html for ${reference}`);
          }
          assets.push(asset);
        }
      }
      setHydrated(assets);
      onAttached?.({
        spawnId: sid,
        references: refs,
        hydrated: assets,
        view_format: "html",
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [spawnId, sessionId, raw, onAttached]);

  /** Residual (agx): insert preset ref (dedupe) without auto-hydrate. */
  const insertPreset = useCallback((reference: string) => {
    const ref = reference.trim();
    if (!ref) return;
    setRaw((prev) => {
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
    setError(null);
  }, []);

  return (
    <section
      className="space-y-2"
      data-testid="publication-attach-panel"
      data-view-format="html"
      data-research-tier={researchTier || ""}
      data-knowledge-dense-presets={String(
        KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
      )}
      data-seamless-pub-quick-call="true"
      data-attach-ready={String(attachReadiness.attach_ready)}
      data-spawn-bound={String(attachReadiness.spawn_bound)}
      data-ref-count={String(attachReadiness.ref_count)}
      data-live-hydrate-deferred={String(
        attachReadiness.live_hydrate_deferred,
      )}
      data-never-auto-hydrate={String(attachReadiness.never_auto_hydrate)}
      aria-label="Attach publication references"
    >
      <header className="space-y-1">
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Attach publications
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          arxiv / substack / URL → attach to spawn + hydrate HTML assets ·
          quick-call presets insert only (offline hydrate until Attach)
        </p>
        {/* Residual (lz): model driver + budget + depth co-display at attach. */}
        <div
          data-testid="publication-attach-driver-badge-mount"
          data-view-format="html"
          data-research-tier={researchTier || ""}
        >
          <DecisionTreeDriverBadge
            researchTier={researchTier}
            promptText={
              raw.trim()
                ? `publication attach · ${raw.trim().slice(0, 2000)}`
                : undefined
            }
          />
        </div>
      </header>
      {/* Residual (agx): knowledge-dense quick-call chips (insert only · never auto-hydrate). */}
      <div
        className="flex flex-wrap gap-1 items-center"
        data-testid="publication-quick-call-presets"
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
            data-testid={`publication-preset-${p.id}`}
            data-preset-id={p.id}
            data-kind={p.kind}
            data-reference={p.reference}
            data-auto-hydrate="false"
            disabled={busy}
            onClick={() => insertPreset(p.reference)}
            className="text-[10px] font-mono border rounded px-1.5 py-0.5 opacity-80 hover:opacity-100 disabled:opacity-50"
            title={`Insert ${p.reference} (does not hydrate until Attach + hydrate)`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <textarea
        data-testid="publication-attach-input"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        disabled={busy}
        rows={2}
        placeholder={"arxiv:1706.03762\nhttps://…"}
        className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[12px] font-mono dark:border-bright/20"
      />
      <p
        className="text-[10px] font-mono opacity-80"
        data-testid="publication-attach-readiness"
        data-attach-ready={String(attachReadiness.attach_ready)}
        data-spawn-bound={String(attachReadiness.spawn_bound)}
        data-ref-count={String(attachReadiness.ref_count)}
        data-view-format={attachReadiness.view_format}
        data-html-first={String(attachReadiness.html_first)}
        data-live-hydrate-deferred={String(
          attachReadiness.live_hydrate_deferred,
        )}
        data-never-auto-hydrate={String(attachReadiness.never_auto_hydrate)}
        role="status"
        title="Knowledge-dense attach path: spawn bound + ≥1 ref · offline hydrate · never auto-hydrate"
      >
        Attach readiness · {attachReadiness.summary}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="publication-attach-submit"
          data-attach-ready={String(attachReadiness.attach_ready)}
          data-spawn-bound={String(attachReadiness.spawn_bound)}
          data-ref-count={String(attachReadiness.ref_count)}
          data-view-format="html"
          data-never-auto-hydrate="true"
          data-live-hydrate-deferred="true"
          disabled={busy || !attachReadiness.attach_ready}
          onClick={() => void run()}
          title={
            attachReadiness.attach_ready
              ? "Attach refs to spawn + hydrate HTML assets (offline-honest · never invent live body)"
              : attachReadiness.summary
          }
          className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
        >
          {busy ? "Attaching…" : "Attach + hydrate"}
        </button>
        {/* Residual (ia): Settings deep-link for env-gated hydrate readiness. */}
        <a
          href="/settings#hydrate-live-status"
          data-testid="publication-attach-settings-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Open Settings → Publication hydrate readiness (arxiv/substack injectors)"
        >
          Settings · hydrate readiness
        </a>
        {/* Residual (mj/xc): dual-gate L1 arxiv checklist section — prep only. */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
          data-testid="publication-attach-dual-gate-checklist-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Dual-gate L1 arxiv hydrate checklist (prep only · offline default)"
        >
          Dual-gate L1 arxiv checklist
        </a>
        {/* Residual (aap): L2 Substack section (parity aal–aao · attach path). */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
          data-testid="publication-attach-dual-gate-l2-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
        >
          Dual-gate L2 Substack checklist
        </a>
        {/* Residual (ajc): knowledge-dense attach → competitive DR honesty map. */}
        <a
          href="/settings#settings-competitive-dr-scorecard"
          data-testid="publication-attach-competitive-scorecard-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Settings competitive deep-research scorecard (source quick-call shipped · live hydrate L1/L2 deferred)"
        >
          Settings · competitive DR scorecard
        </a>
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
          data-testid="publication-attach-competitive-dr-future-agent-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="FUTURE-AGENT competitive deep-research quality brief"
        >
          FUTURE · competitive DR brief
        </a>
        {/* Residual (ald): knowledge-dense attach budget-before-fire → prompt-cost. */}
        <a
          href="/settings#prompt-cost-projection"
          data-testid="publication-attach-prompt-cost-projection-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Settings prompt-cost projection: estimate how arxiv/substack attach+hydrate spend hits remaining daily budget"
        >
          Settings · prompt-cost projection
        </a>
      </div>
      {error ? (
        <p className="text-[11px] font-mono text-emperor" role="alert">
          {error}
        </p>
      ) : null}
      {attached.length > 0 ? (
        <div
          className="text-[11px] font-mono space-y-1"
          data-testid="publication-attach-result"
          data-view-format="html"
          data-citation-trust={hydrated.length > 0 ? "grounded" : "ungrounded"}
          data-hydrated-count={String(hydrated.length)}
          data-research-tier={researchTier || ""}
          data-offline-honest-count={String(
            hydrated.filter((a) => a.offline_honest !== false && !a.fetched)
              .length,
          )}
        >
          {/* Residual (hz/ko): machine-readable attach+hydrate + depth metrics. */}
          <div
            data-testid="publication-attach-metrics"
            data-attached-count={String(attached.length)}
            data-hydrated-count={String(hydrated.length)}
            data-offline-honest-count={String(
              hydrated.filter((a) => a.offline_honest !== false && !a.fetched)
                .length,
            )}
            data-citation-trust={
              hydrated.length > 0 ? "grounded" : "ungrounded"
            }
            data-research-tier={researchTier || ""}
            data-view-format="html"
            role="status"
          >
            Publication attach · attached={attached.length} · hydrated=
            {hydrated.length} · trust=
            {hydrated.length > 0 ? "grounded" : "ungrounded"}
            {researchTier ? ` · tier=${researchTier}` : ""}
          </div>
          <p>
            Attached {attached.length} · hydrated {hydrated.length} HTML asset(s)
          </p>
          {/* Residual (ko): spawn research_tier depth posture after attach. */}
          {researchTier ? (
            <p
              className="opacity-90"
              data-testid="publication-attach-research-tier"
              data-research-tier={researchTier}
              role="status"
            >
              Research tier: <strong>{researchTier}</strong>
              {researchTier === "wrestle"
                ? " · multi-minute long-horizon depth"
                : researchTier === "fast"
                  ? " · flash / distill depth"
                  : " · deep / synthesize depth"}
            </p>
          ) : null}
          {/* Residual (ef/uq): competitive bar — attached pubs are citation ground. */}
          <div
            className={
              hydrated.length > 0
                ? "text-aurora space-y-1"
                : "text-emperor space-y-1"
            }
            data-testid="publication-attach-citation-trust"
            data-citation-trust={
              hydrated.length > 0 ? "grounded" : "ungrounded"
            }
            data-offline-hydrate-default="true"
            role="status"
          >
            <p>
              {hydrated.length > 0
                ? `Citation trust: grounded · ${hydrated.length} HTML publication asset(s)`
                : "Citation trust: ungrounded — hydrate failed; re-attach refs"}
            </p>
            {/* Residual (uq/vb): hydrate prep links for both ungrounded + grounded. */}
            <p className="space-x-2 opacity-90">
              <a
                href="/settings#hydrate-live-status"
                data-testid="publication-attach-hydrate-settings-link"
                className="underline hover:opacity-100"
                title="Settings publication hydrate readiness (arxiv/substack · offline default)"
              >
                Settings · hydrate readiness
              </a>
              {/* Residual (xc): L1 arxiv checklist section deep-link. */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
                data-testid="publication-attach-hydrate-dual-gate-link"
                className="underline hover:opacity-100"
                title="Dual-gate L1 arxiv hydrate checklist (prep only · offline default)"
              >
                Dual-gate L1 arxiv checklist
              </a>
              {/* Residual (aap): L2 Substack section (maintain-prep after attach). */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
                data-testid="publication-attach-hydrate-dual-gate-l2-link"
                className="underline hover:opacity-100"
                title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
              >
                Dual-gate L2 Substack checklist
              </a>
            </p>
          </div>
          {/* Residual (hc): offline-honest identity vs injector body. */}
          {hydrated.length > 0 ? (
            <p
              className="text-ink-soft dark:text-starlight"
              data-testid="publication-attach-offline-honest"
              role="status"
            >
              {(() => {
                const offlineN = hydrated.filter(
                  (a) => a.offline_honest !== false && !a.fetched,
                ).length;
                const liveN = hydrated.length - offlineN;
                if (offlineN > 0 && liveN === 0) {
                  return `Hydrate mode: offline-honest identity (${offlineN}) — no live body; not invented abstract`;
                }
                if (offlineN === 0 && liveN > 0) {
                  return `Hydrate mode: injector body landed (${liveN})`;
                }
                return `Hydrate mode: mixed · offline-honest=${offlineN} · injector=${liveN}`;
              })()}
            </p>
          ) : null}
          {/* Residual (rc/acs): hydrated pubs → Write twin_seed + body honesty. */}
          {hydrated.length > 0
            ? (() => {
                const href = buildPublicationHydrateWriteHref({
                  spawnId,
                  assets: hydrated,
                });
                const hasBody = hydrated.some(
                  (a) =>
                    Boolean(String(a.body_text || "").trim()) ||
                    Boolean(plainTextFromHtml(a.html || "").trim()),
                );
                return href ? (
                  <p>
                    <a
                      href={href}
                      data-testid="publication-attach-open-write"
                      data-view-format="html"
                      data-has-twin-seed="1"
                      data-hydrated-count={String(hydrated.length)}
                      data-write-seed-has-body={String(hasBody)}
                      className="underline opacity-90 hover:opacity-100"
                      title="Open Write with hydrated publications as twin_seed (arxiv/substack/URL; no invented document_id)"
                    >
                      Open Write (publications)
                    </a>
                  </p>
                ) : null;
              })()
            : null}
          <ul data-testid="publication-attach-asset-list">
            {hydrated.map((a) => {
              const offline =
                a.offline_honest !== false && a.fetched !== true;
              return (
                <li
                  key={a.asset_id}
                  data-testid={`publication-attach-asset-${a.asset_id}`}
                  data-offline-honest={offline ? "true" : "false"}
                  data-fetched={String(Boolean(a.fetched))}
                >
                  <code>{a.asset_id}</code> · {a.title} · fetched=
                  {String(a.fetched)}
                  {offline ? " · offline-honest" : " · body landed"}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default PublicationAttachPanel;
