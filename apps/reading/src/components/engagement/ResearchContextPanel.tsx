/**
 * ResearchContextPanel — workstation chrome for twin + source-ref context.
 *
 * Loads a ResearchContextPack from /engagement/research-context and renders
 * the prompt block for injection into the next deep-research turn.
 * HTML-first stance: this panel never offers PDF export.
 */

import { useCallback, useState } from "react";
import {
  attachSourceRefs,
  fetchEvidencePack,
  fetchResearchContext,
  hydratePublicationRef,
  type EvidencePackResponse,
  type HydrateRefResponse,
  type ResearchContextResponse,
} from "../../api/engagement";
import { detectSourceKindClient } from "../../workspace/researchContextPack";

export type ResearchContextPanelProps = {
  assetId: string;
  spawnId?: string | null;
  /** Optional controlled initial query filter */
  initialQuery?: string;
};

export function ResearchContextPanel({
  assetId,
  spawnId = null,
  initialQuery = "",
}: ResearchContextPanelProps) {
  const [query, setQuery] = useState(initialQuery);
  const [refInput, setRefInput] = useState("");
  const [pack, setPack] = useState<ResearchContextResponse | null>(null);
  const [evidence, setEvidence] = useState<EvidencePackResponse | null>(null);
  const [hydrated, setHydrated] = useState<HydrateRefResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <section
      className="research-context-panel"
      data-view-format="html"
      data-testid="research-context-panel"
      aria-label="Research context"
    >
      <header>
        <h2>Research context</h2>
        <p className="meta">
          asset <code>{assetId}</code>
          {spawnId ? (
            <>
              {" "}
              · spawn <code>{spawnId}</code>
            </>
          ) : null}
        </p>
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
        <button type="button" onClick={() => void load()} disabled={busy}>
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
        <div className="pack">
          <p className="counts">
            twins={pack.twin_count ?? pack.twin_units?.length ?? 0} · refs=
            {pack.ref_count ?? pack.source_references?.length ?? 0}
          </p>
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
        >
          <p className="counts">
            evidence · insights={evidence.insight_count} · questions=
            {evidence.question_count} · refs={evidence.ref_count}
          </p>
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
        >
          <p>
            hydrated asset <code>{hydrated.asset_id}</code> · fetched=
            {String(hydrated.fetched)} · {hydrated.title}
          </p>
          {hydrated.html ? (
            <div
              data-testid="hydrate-ref-html"
              dangerouslySetInnerHTML={{ __html: hydrated.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default ResearchContextPanel;
