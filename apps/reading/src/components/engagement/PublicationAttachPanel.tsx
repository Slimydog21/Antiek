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
 * before/after attach (prop tier preferred; attach response fills when known).
 * Residual (mj): dual-gate L1–L4 checklist deep-link for arxiv/substack
 * live-injector dogfood prep (never enables injectors).
 * HTML-first; offline hydrate by default.
 */

import { useCallback, useMemo, useState } from "react";
import {
  attachSourceRefs,
  hydratePublicationRef,
  type HydrateRefResponse,
} from "../../api/engagement";
import {
  parsePublicationRefs,
} from "../../modes/ResearchWorkstation/publicationRefs";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

export type PublicationAttachResult = {
  spawnId: string;
  references: string[];
  hydrated: HydrateRefResponse[];
  view_format: "html";
};

export type PublicationAttachPanelProps = {
  spawnId: string;
  /** Residual (ed): fire after successful attach+hydrate (HTML assets only). */
  onAttached?: (result: PublicationAttachResult) => void;
  /**
   * Residual (lz): session/spawn research tier for driver co-display.
   * Prop wins over attach-response tier when both present.
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function PublicationAttachPanel({
  spawnId,
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

  const run = useCallback(async () => {
    const sid = spawnId.trim();
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
      const attach = await attachSourceRefs(sid, refs);
      if (attach.view_format !== "html") {
        throw new Error("attach view_format must be html");
      }
      setAttached(refs);
      // Residual (ko): reserved spawn research_tier from attach response.
      setAttachResearchTier(
        (attach.research_tier || "").trim().toLowerCase() || null,
      );
      const assets: HydrateRefResponse[] = [];
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
  }, [spawnId, raw, onAttached]);

  return (
    <section
      className="space-y-2"
      data-testid="publication-attach-panel"
      data-view-format="html"
      data-research-tier={researchTier || ""}
      aria-label="Attach publication references"
    >
      <header className="space-y-1">
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Attach publications
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          arxiv / substack / URL → attach to spawn + hydrate HTML assets
        </p>
        {/* Residual (lz): model driver + budget + depth co-display at attach. */}
        <div
          data-testid="publication-attach-driver-badge-mount"
          data-view-format="html"
          data-research-tier={researchTier || ""}
        >
          <DecisionTreeDriverBadge researchTier={researchTier} />
        </div>
      </header>
      <textarea
        data-testid="publication-attach-input"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        disabled={busy}
        rows={2}
        placeholder={"arxiv:1706.03762\nhttps://…"}
        className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[12px] font-mono dark:border-bright/20"
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          data-testid="publication-attach-submit"
          disabled={busy || !raw.trim()}
          onClick={() => void run()}
          className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
        >
          {busy ? "Attaching…" : "Attach + hydrate"}
        </button>
        {/* Residual (ia): Settings deep-link for env-gated hydrate readiness. */}
        <a
          href="/settings"
          data-testid="publication-attach-settings-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Open Settings → Publication hydrate readiness (arxiv/substack injectors)"
        >
          Settings · hydrate readiness
        </a>
        {/* Residual (mj): dual-gate checklist — prep only, never enables L1–L4. */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
          data-testid="publication-attach-dual-gate-checklist-link"
          className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
          title="Dual-gate L1–L4 operator checklist (env+injector prep; offline default)"
        >
          Dual-gate L1–L4 checklist
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
          {/* Residual (ef): competitive bar — attached pubs are citation ground. */}
          <p
            className={
              hydrated.length > 0
                ? "text-aurora"
                : "text-emperor"
            }
            data-testid="publication-attach-citation-trust"
            role="status"
          >
            {hydrated.length > 0
              ? `Citation trust: grounded · ${hydrated.length} HTML publication asset(s)`
              : "Citation trust: ungrounded — hydrate failed; re-attach refs"}
          </p>
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
