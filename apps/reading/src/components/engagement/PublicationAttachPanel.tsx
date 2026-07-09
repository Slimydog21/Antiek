/**
 * PublicationAttachPanel — attach + hydrate arxiv/substack/url onto a spawn.
 *
 * Residual (ck): mid-session knowledge-dense publication attach for deep
 * research windows. Composes attachSourceRefs + hydratePublicationRef.
 * HTML-first; offline hydrate by default.
 */

import { useCallback, useState } from "react";
import {
  attachSourceRefs,
  hydratePublicationRef,
  type HydrateRefResponse,
} from "../../api/engagement";
import {
  parsePublicationRefs,
} from "../../modes/ResearchWorkstation/publicationRefs";

export type PublicationAttachPanelProps = {
  spawnId: string;
};

export function PublicationAttachPanel({ spawnId }: PublicationAttachPanelProps) {
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attached, setAttached] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState<HydrateRefResponse[]>([]);

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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [spawnId, raw]);

  return (
    <section
      className="space-y-2"
      data-testid="publication-attach-panel"
      data-view-format="html"
      aria-label="Attach publication references"
    >
      <header>
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Attach publications
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          arxiv / substack / URL → attach to spawn + hydrate HTML assets
        </p>
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
      <button
        type="button"
        data-testid="publication-attach-submit"
        disabled={busy || !raw.trim()}
        onClick={() => void run()}
        className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
      >
        {busy ? "Attaching…" : "Attach + hydrate"}
      </button>
      {error ? (
        <p className="text-[11px] font-mono text-emperor" role="alert">
          {error}
        </p>
      ) : null}
      {attached.length > 0 ? (
        <div
          className="text-[11px] font-mono space-y-1"
          data-testid="publication-attach-result"
        >
          <p>
            Attached {attached.length} · hydrated {hydrated.length} HTML asset(s)
          </p>
          <ul>
            {hydrated.map((a) => (
              <li key={a.asset_id}>
                <code>{a.asset_id}</code> · {a.title} · fetched=
                {String(a.fetched)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default PublicationAttachPanel;
