import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  getCanonicalMergeHtml,
  type CanonicalMergeHtmlResponse,
} from "../../../api/engagement";
import { ResearchContextPanel } from "../../../components/engagement/ResearchContextPanel";
import { TwinNotesPanel } from "../../../components/engagement/TwinNotesPanel";
import { sanitizeHostedHtml } from "../../../lib/sanitizeHostedHtml";

export default function CanonicalResearch() {
  const { deliverableId = "" } = useParams<{ deliverableId: string }>();
  const navigate = useNavigate();
  const [asset, setAsset] = useState<CanonicalMergeHtmlResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [contextRefreshKey, setContextRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setAsset(null);
    void getCanonicalMergeHtml(deliverableId)
      .then((response) => {
        if (!active) return;
        if (response.view_format !== "html" || !response.html?.trim()) {
          throw new Error("canonical research did not return HTML");
        }
        if (
          response.deliverable_id !== deliverableId ||
          response.twin_note_count < 1
        ) {
          throw new Error("canonical research authority response is inconsistent");
        }
        setAsset(response);
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deliverableId]);

  return (
    <main
      className="mx-auto max-w-4xl space-y-4 px-6 py-8"
      data-testid="canonical-research-reader"
      data-deliverable-id={deliverableId}
      data-view-format="html"
    >
      <header className="space-y-2 border-b border-rule pb-3 dark:border-charcoal-1">
        <p className="text-[11px] font-mono uppercase tracking-wide text-shadow-1">
          Canonical research
        </p>
        <h1 className="break-all text-xl font-serif">{deliverableId}</h1>
        {asset ? (
          <p
            className="break-all text-[10px] font-mono text-shadow-1"
            data-testid="canonical-research-authority"
          >
            revision {asset.revision} · reviewed hash {asset.draft_sha256}
          </p>
        ) : null}
        <button
          type="button"
          onClick={() => navigate(`/write/${encodeURIComponent(deliverableId)}`)}
          disabled={!asset}
          className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono disabled:opacity-50"
        >
          Open canonical in Write
        </button>
      </header>
      {loading ? <p role="status">Loading canonical research…</p> : null}
      {error ? <p role="alert" className="text-emperor">{error}</p> : null}
      {asset ? (
        <>
          <article
            className="prose max-w-none dark:prose-invert"
            data-testid="canonical-research-html"
            dangerouslySetInnerHTML={{ __html: sanitizeHostedHtml(asset.html) }}
          />
          <section
            className="rounded-md border border-rule bg-ice-0 px-3 py-2 dark:border-charcoal-1 dark:bg-charcoal-2"
            data-testid="canonical-research-twins-mount"
            data-asset-id={asset.deliverable_id}
          >
            <TwinNotesPanel
              assetId={asset.deliverable_id}
              autoLoad
              autoPromoteAfterLoad
              onPromoted={() => setContextRefreshKey((value) => value + 1)}
            />
          </section>
          <section
            className="rounded-md border border-rule bg-ice-0 px-3 py-2 dark:border-charcoal-1 dark:bg-charcoal-2"
            data-testid="canonical-research-context-mount"
            data-asset-id={asset.deliverable_id}
            data-refresh-key={String(contextRefreshKey)}
          >
            <ResearchContextPanel
              key={`canonical-context-${asset.deliverable_id}-${contextRefreshKey}`}
              assetId={asset.deliverable_id}
              autoLoad
            />
          </section>
        </>
      ) : null}
    </main>
  );
}
