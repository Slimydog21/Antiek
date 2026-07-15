import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getDerivedAssetReading, getDerivedEvidenceCollection } from "../../api/research";
import type { DerivedAssetReadingResponse } from "../../api/research";
import type { DerivedCompanionCitation } from "../../api/research";
import type { DerivedEvidenceCollection } from "../../api/research";
import { LemonButton, LemonTag } from "../../components/lemon";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import DerivedRevisionCompanion from "./DerivedRevisionCompanion";

const ASSET_ID = /^ast_[0-9a-f]{32}$/;
const REVISION_ID = /^rev_[0-9a-f]{32}$/;
const COLLECTION_ID = /^dec_[0-9a-f]{32}$/;

export default function DerivedAssetReader() {
  const { assetId = "", revisionId, collectionId } = useParams<{
    assetId?: string; revisionId?: string; collectionId?: string;
  }>();
  const openPanel = useWorkspace((state) => state.open);
  const articleRef = useRef<HTMLElement>(null);
  const requestGeneration = useRef(0);
  const [model, setModel] = useState<DerivedAssetReadingResponse | null>(null);
  const [collection, setCollection] = useState<DerivedEvidenceCollection | null>(null);
  const [committedRouteKey, setCommittedRouteKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const routeKey = collectionId === undefined
    ? `asset:${assetId}:revision:${revisionId ?? "current"}`
    : `collection:${collectionId}`;

  const load = useCallback(async () => {
    const generation = ++requestGeneration.current;
    window.getSelection()?.removeAllRanges();
    setLoading(true);
    setError(null);
    setLocationError(null);
    setModel(null);
    setCollection(null);
    setCommittedRouteKey(null);
    if ((collectionId !== undefined && !COLLECTION_ID.test(collectionId))
        || (collectionId === undefined && (!ASSET_ID.test(assetId)
          || (revisionId !== undefined && !REVISION_ID.test(revisionId))))) {
      setError("This reading link is invalid.");
      setCommittedRouteKey(routeKey);
      setLoading(false);
      return;
    }
    try {
      const selectedCollection = collectionId === undefined
        ? null : await getDerivedEvidenceCollection(collectionId);
      if (generation !== requestGeneration.current) return;
      const requestedAssetId = selectedCollection?.derived_asset_id ?? assetId;
      const requestedRevisionId = selectedCollection?.revision_id ?? revisionId;
      if (!ASSET_ID.test(requestedAssetId)
          || (requestedRevisionId !== undefined && !REVISION_ID.test(requestedRevisionId))) {
        throw new Error("collection reading identity conflict");
      }
      const next = await getDerivedAssetReading(requestedAssetId, requestedRevisionId);
      if (generation !== requestGeneration.current) return;
      const expectedExact = `/read/derived/${requestedAssetId}/revisions/${next.revision_id}`;
      const sourceIdentities = new Set(selectedCollection?.sources.map(
        (source) => source.citation_id,
      ));
      const collectionConflict = selectedCollection !== null && (
        selectedCollection.collection_id !== collectionId
        || selectedCollection.derived_asset_id !== next.derived_asset_id
        || selectedCollection.revision_id !== next.revision_id
        || selectedCollection.content_sha256 !== next.content_sha256
        || selectedCollection.generation !== next.generation
        || selectedCollection.member_count !== selectedCollection.sources.length
        || selectedCollection.member_count < 2 || selectedCollection.member_count > 6
        || selectedCollection.sources.length !== selectedCollection.locations.length
        || sourceIdentities.size !== selectedCollection.sources.length
        || selectedCollection.sources.some((source) =>
          source.derived_asset_id !== selectedCollection.derived_asset_id
          || source.revision_id !== selectedCollection.revision_id
          || source.content_sha256 !== selectedCollection.content_sha256
          || source.generation !== selectedCollection.generation)
        || selectedCollection.sources.some((source, index) => {
          const location = selectedCollection.locations[index];
          return source.citation_id !== location?.citation_id
            || source.chunk_ordinal !== location.chunk_ordinal
            || !Number.isInteger(location.member_index) || location.member_index < 0
            || typeof location.section_anchor !== "string"
            || location.section_anchor.length === 0;
        })
      );
      if (next.derived_asset_id !== requestedAssetId
          || (requestedRevisionId !== undefined && next.revision_id !== requestedRevisionId)
          || next.stable_reader_path !== `/read/derived/${requestedAssetId}`
          || next.exact_reader_path !== expectedExact
          || !REVISION_ID.test(next.revision_id)
          || !/^[0-9a-f]{64}$/.test(next.content_sha256)
          || !Number.isInteger(next.generation) || next.generation < 1
          || collectionConflict) {
        throw new Error("reading identity conflict");
      }
      setModel(next);
      setCollection(selectedCollection);
      setCommittedRouteKey(routeKey);
    } catch {
      if (generation === requestGeneration.current) {
        setError("This derived asset could not be verified for reading.");
        setCommittedRouteKey(routeKey);
      }
    } finally {
      if (generation === requestGeneration.current) setLoading(false);
    }
  }, [assetId, revisionId, collectionId, routeKey]);

  useEffect(() => {
    void load();
    return () => { requestGeneration.current += 1; };
  }, [load]);

  const selection = useFloatMenuSelection({
    scopeRef: articleRef,
    minLength: 8,
    resolveProvenance: () => ({
      documentId: model?.derived_asset_id ?? null,
      chunkId: null,
      servable: model !== null,
      derivedRevisionId: model?.revision_id ?? null,
      derivedContentSha256: model?.content_sha256 ?? null,
      derivedGeneration: model?.generation ?? null,
    }),
  });

  const onDeepResearch = useCallback((text: string | null, selected: FloatMenuSelection) => {
    if (!text || !model) return;
    window.getSelection()?.removeAllRanges();
    openPanel("ChaseThread", {
      spawnContext: text,
      parentInvestigationId: `read-${model.derived_asset_id}:${model.revision_id}`,
      sourceProvenance: selected.provenance,
    }, { mode: "floating", title: "Follow this" });
  }, [model, openPanel]);

  const onFollowCitation = useCallback((citation: DerivedCompanionCitation) => {
    if (!model) return;
    openPanel("ChaseThread", {
      spawnContext: citation.text,
      parentInvestigationId: `read-${model.derived_asset_id}:${model.revision_id}`,
      sourceProvenance: {
        documentId: model.derived_asset_id,
        chunkId: null,
        servable: true,
        derivedRevisionId: model.revision_id,
        derivedContentSha256: model.content_sha256,
        derivedGeneration: model.generation,
        derivedCitationId: citation.citation_id,
        derivedChunkOrdinal: citation.chunk_ordinal,
        derivedChunkTextSha256: citation.text_sha256,
      },
    }, { mode: "floating", title: "Follow this" });
  }, [model, openPanel]);

  const onResearchCitations = useCallback((citations: DerivedCompanionCitation[]) => {
    if (!model || citations.length < 2 || citations.length > 6) return;
    const context = citations.map(
      (citation, index) => `[Evidence ${index + 1} of ${citations.length}]\n${citation.text}`,
    ).join("\n\n");
    openPanel("ChaseThread", {
      spawnContext: context,
      parentInvestigationId: `read-${model.derived_asset_id}:${model.revision_id}`,
      sourceSelections: citations.map((citation) => ({
        text: citation.text,
        provenance: {
          documentId: model.derived_asset_id, chunkId: null, servable: true,
          derivedRevisionId: model.revision_id,
          derivedContentSha256: model.content_sha256,
          derivedGeneration: model.generation,
          derivedCitationId: citation.citation_id,
          derivedChunkOrdinal: citation.chunk_ordinal,
          derivedChunkTextSha256: citation.text_sha256,
        },
      })),
    }, { mode: "floating", title: "Research passages" });
  }, [model, openPanel]);

  const onResearchCollection = useCallback((collection: DerivedEvidenceCollection) => {
    if (!model || collection.derived_asset_id !== model.derived_asset_id) return;
    const context = collection.sources.map(
      (source, index) => `[Evidence ${index + 1} of ${collection.sources.length}]\n${source.excerpt}`,
    ).join("\n\n");
    openPanel("ChaseThread", {
      spawnContext: context,
      parentInvestigationId: `read-${collection.derived_asset_id}:${collection.revision_id}`,
      evidenceCollection: { collectionId: collection.collection_id, etag: collection.etag },
      sourceSelections: collection.sources.map((source) => ({
        text: source.excerpt,
        provenance: {
          documentId: source.derived_asset_id, chunkId: null, servable: true,
          derivedRevisionId: source.revision_id,
          derivedContentSha256: source.content_sha256,
          derivedGeneration: source.generation,
          derivedCitationId: source.citation_id,
          derivedChunkOrdinal: source.chunk_ordinal,
          derivedChunkTextSha256: source.chunk_text_sha256,
        },
      })),
    }, { mode: "floating", title: collection.label });
  }, [model, openPanel]);

  const showCollectionLocation = useCallback((anchor: string) => {
    const target = Array.from(
      articleRef.current?.querySelectorAll<HTMLElement>("[id]") ?? [],
    ).find((candidate) => candidate.id === anchor);
    if (!target) {
      setLocationError("This saved passage no longer has a verified location in the reading.");
      return;
    }
    setLocationError(null);
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.animate(
      [{ outline: "3px solid #f9bd2b" }, { outline: "3px solid transparent" }],
      { duration: 1800, easing: "ease-out" },
    );
  }, []);

  if (loading || committedRouteKey !== routeKey) return <main className="flex min-h-[60vh] items-center justify-center text-sm text-shadow-1">Opening the asset...</main>;
  if (error || !model) return <main className="flex min-h-[60vh] flex-col items-center justify-center gap-3"><p role="alert" className="text-sm text-emperor">{error}</p><Link to="/" className="text-sm underline">Return to research</Link></main>;

  const threadId = `read-${model.derived_asset_id}:${model.revision_id}`;
  return <div className="flex h-full min-h-0 bg-ice-0 dark:bg-charcoal-2">
    <main className="min-w-0 flex-1 overflow-y-auto">
      <header className="sticky top-0 z-10 border-b border-rule bg-ice-0/95 px-5 py-3 backdrop-blur dark:border-charcoal-1 dark:bg-charcoal-2/95">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <Link to="/" aria-label="Return to research" title="Return to research"><ArrowLeft size={18} /></Link>
          <div className="min-w-0 flex-1"><h1 className="truncate font-serif text-lg text-ink dark:text-bright">{model.title}</h1><p className="truncate font-mono text-[10px] text-shadow-1 dark:text-moonlight">{model.revision_id} · {model.content_sha256.slice(0, 12)} · generation {model.generation}</p></div>
          <LemonTag colour={model.is_current ? "aurora" : "sun"}>{model.is_current ? "Current" : "Historical"}</LemonTag>
          <LemonTag colour="muted">{model.asset_kind}</LemonTag>
          {model.is_current ? <LemonButton type="button" variant="tertiary" size="sm" title="Refresh current revision" aria-label="Refresh current revision" onClick={() => void load()}><RefreshCw size={15} /></LemonButton> : <Link to={model.stable_reader_path} className="inline-flex items-center gap-1 text-xs underline">Current <ExternalLink size={13} /></Link>}
        </div>
      </header>
      {collection ? <section aria-label="Opened evidence collection" className="border-b border-rule bg-white px-6 py-4 dark:border-charcoal-1 dark:bg-charcoal-3">
        <div className="mx-auto max-w-3xl"><div className="flex items-center justify-between gap-3"><div><h2 className="font-serif text-sm font-semibold text-ink dark:text-bright">{collection.label}</h2><p className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">{collection.member_count} saved passages · exact revision</p></div><LemonButton type="button" size="sm" onClick={() => onResearchCollection(collection)}>Research collection</LemonButton></div>
          <ol className="mt-3 grid gap-2">{collection.sources.map((source, index) => <li key={source.citation_id}><button type="button" onClick={() => showCollectionLocation(collection.locations[index].section_anchor)} className="w-full border-l-2 border-sun px-3 py-2 text-left"><span className="block font-mono text-[10px] text-shadow-1 dark:text-moonlight">{index + 1}. {collection.locations[index].section_path || "Saved passage"}</span><span className="mt-1 line-clamp-2 block font-serif text-xs text-ink dark:text-bright">{source.excerpt}</span></button></li>)}</ol>
        </div>
      </section> : null}
      {locationError ? <p role="alert" className="mx-auto max-w-3xl px-6 pt-4 text-sm text-danger">{locationError}</p> : null}
      <article ref={articleRef} className="derived-html-reading prose prose-neutral mx-auto max-w-3xl px-6 py-10 font-serif text-ink dark:prose-invert dark:text-bright" data-derived-asset-id={model.derived_asset_id} data-revision-id={model.revision_id} data-content-sha256={model.content_sha256} dangerouslySetInnerHTML={{ __html: model.canonical_html }} />
    </main>
    <DerivedRevisionCompanion model={model} articleRef={articleRef} onFollowCitation={onFollowCitation} onResearchCitations={onResearchCitations} onResearchCollection={onResearchCollection} />
    <FloatMenu selection={selection} investigationId={threadId} onDeepResearch={onDeepResearch} />
  </div>;
}
