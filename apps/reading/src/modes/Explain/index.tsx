import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import type {
  ChunkPin,
  ClaimExplainResponse,
  DocumentExplainResponse,
  DocumentPin,
  EdgePin,
  ExplainChunk,
  ExplainDocument,
  ExplainEdge,
  ExplainNode,
  NodePin,
  SynthesisExplainResponse,
  TierOverride,
} from "../../api/ownYourMind";
import {
  explainClaim,
  explainDocument,
  explainSynthesis,
} from "../../api/ownYourMind";
import { createTierOverride, getTierOverrides } from "../../api/tiers";
import { useServedImpression } from "../../lib/servedImpression";

/**
 * Explain — the "why this claim" provenance panel (Own Your Mind P0, D1).
 *
 * Route: /explain/:kind/:id where kind ∈ claim | synthesis | document.
 * Read-only: renders the backend's provenance chains (GET
 * /claims/{id}/explain, /syntheses/{id}/explain, /docs/{id}/explain),
 * never mutates:
 *
 *   claim      → the claim node, its supporting edges (relation, tier,
 *                confidence), each chunk's excerpt with a document link,
 *                and any chunk-tier overrides (set_by / reason).
 *   synthesis  → what grounded the synthesis: the
 *                synthesis_substrate_manifest pins grouped by entity kind
 *                (each pin resolved to its own chain; unresolved pins are
 *                surfaced honestly, never dropped).
 *   document   → reverse provenance: the document's chunks and the edges
 *                that cite them (each citing claim links back into
 *                /explain/claim/:id).
 *
 * Every item links to an existing surface — /read/:documentId (BookReader),
 * /backtest/:synthesisId — never to a dead route.
 */

type ExplainKind = "claim" | "synthesis" | "document";

const KIND_META: Record<ExplainKind, { title: string; lede: string }> = {
  claim: {
    title: "Why this claim",
    lede:
      "The grounding chain behind this claim — the edges that support it, " +
      "the source chunks those edges cite, and who retiered any of them.",
  },
  synthesis: {
    title: "What grounded this synthesis",
    lede:
      "The substrate manifest this synthesis pinned at archive time — " +
      "documents, chunks, nodes, and edges — each resolved to its chain.",
  },
  document: {
    title: "Who cites this document",
    lede:
      "Reverse provenance: the chunks this document contributed and every " +
      "claim whose edges cite those chunks as evidence.",
  },
};

/** Tier chip — 1 strongest … 5 weakest (same semantics + tokens as the
 *  ResearchWorkstation ChunkModal chip). */
function TierChip({ tier }: { tier: number }) {
  const colorClass =
    tier === 1
      ? "bg-emerald-100 text-emerald-800"
      : tier === 2
        ? "bg-emerald-50 text-emerald-700"
        : tier === 3
          ? "bg-sun/10 text-sun-deep dark:text-sun"
          : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded ${colorClass}`}
    >
      tier {tier}
    </span>
  );
}

/** Confidence chip — 0..1 extraction confidence as a percent, banded. */
function ConfidenceChip({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const colorClass =
    confidence >= 0.8
      ? "bg-emerald-100 text-emerald-800"
      : confidence >= 0.6
        ? "bg-sun/10 text-sun-deep dark:text-sun"
        : "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight";
  return (
    <span
      className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded ${colorClass}`}
      title={`extraction confidence ${confidence.toFixed(3)}`}
    >
      {pct}% confidence
    </span>
  );
}

/** A chunk excerpt with its section path + the tier of its source document. */
function ChunkBlock({
  chunk,
  document,
  onTierChanged,
}: {
  chunk: ExplainChunk;
  document: ExplainDocument;
  onTierChanged?: () => void;
}) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap text-xs">
        {chunk.section_path && (
          <span className="font-mono text-shadow-1 dark:text-moonlight">
            {chunk.section_path}
          </span>
        )}
        {chunk.chunk_index !== null && (
          <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
            chunk {chunk.chunk_index}
          </span>
        )}
        <TierChip tier={document.source_tier} />
      </div>
      <p className="text-sm text-ink dark:text-bright font-serif leading-relaxed whitespace-pre-wrap">
        {chunk.text}
      </p>
      <DocumentLink document={document} />
      <SetTierControl
        chunkId={chunk.chunk_id}
        currentTier={document.source_tier}
        onCreated={onTierChanged ?? (() => undefined)}
      />
    </div>
  );
}

function DocumentLink({ document }: { document: ExplainDocument }) {
  const title = document.title ?? document.document_id;
  return (
    <div className="flex items-center gap-2 flex-wrap text-xs">
      <Link
        to={`/read/${encodeURIComponent(document.document_id)}`}
        className="font-mono text-ink dark:text-bright hover:text-sun-deep dark:hover:text-sun underline decoration-dotted underline-offset-2"
      >
        {title}
      </Link>
      {document.author && (
        <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
          {document.author}
        </span>
      )}
      {document.acquired_at && (
        <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
          acquired {new Date(document.acquired_at).toLocaleDateString()}
        </span>
      )}
    </div>
  );
}

/**
 * SetTierControl — the user-settable write half (OYM P1 §5).
 *
 * Revealed by a "Set tier" button on every chunk row that carries tier
 * chips: a small form (tier 1..5 + mandatory reason) that POSTs one
 * append-only override row, then asks the parent to reload the explain
 * chain so the new override badge appears. The chunk's existing override
 * history (set_by / reason / date, newest first) is listed from GET
 * /settings/tier-overrides when the control opens.
 */
function SetTierControl({
  chunkId,
  currentTier,
  onCreated,
}: {
  chunkId: string;
  currentTier: number;
  onCreated: () => void;
}) {
  const [open, setOpen] = useState<boolean>(false);
  const [tier, setTier] = useState<number>(
    currentTier >= 1 && currentTier <= 5 ? currentTier : 3,
  );
  const [reason, setReason] = useState<string>("");
  const [overrides, setOverrides] = useState<TierOverride[] | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverrides = useCallback(async () => {
    setError(null);
    try {
      const res = await getTierOverrides(chunkId);
      setOverrides(res.overrides);
    } catch (e: unknown) {
      setOverrides(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [chunkId]);

  const toggle = () => {
    setOpen((wasOpen) => {
      if (!wasOpen) void loadOverrides();
      return !wasOpen;
    });
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await createTierOverride(chunkId, tier, reason);
      setReason("");
      await loadOverrides();
      // The parent reloads the explain chain so the new override badge
      // appears next to the chunk's tier chips.
      onCreated();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pt-1">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="text-[10px] font-mono uppercase tracking-wide text-ink-soft dark:text-starlight hover:text-sun-deep dark:hover:text-sun underline decoration-dotted underline-offset-2"
      >
        {open ? "hide tier history" : "set tier"}
      </button>
      {open && (
        <div className="mt-2 border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 space-y-2">
          <div className="flex items-end gap-2 flex-wrap">
            <label className="flex flex-col gap-1 text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              override tier
              <select
                value={tier}
                onChange={(e) => setTier(Number(e.target.value))}
                aria-label="override tier"
                className="border border-rule dark:border-charcoal-1 rounded px-2 py-1 text-xs font-sans normal-case tracking-normal text-ink dark:text-bright bg-ice-0 dark:bg-charcoal-2"
              >
                {[1, 2, 3, 4, 5].map((value) => (
                  <option key={value} value={value}>
                    tier {value}
                    {value === 1
                      ? " — strongest"
                      : value === 5
                        ? " — weakest"
                        : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight grow">
              reason (audit trail)
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="why this retiering?"
                aria-label="reason for tier override"
                className="border border-rule dark:border-charcoal-1 rounded px-2 py-1 text-xs font-sans normal-case tracking-normal text-ink dark:text-bright bg-ice-0 dark:bg-charcoal-2 w-full"
              />
            </label>
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || reason.trim() === ""}
              className="text-[10px] font-mono uppercase tracking-wide px-2 py-1 rounded bg-sun/15 dark:bg-sun/20 text-sun-deep dark:text-sun disabled:opacity-40"
            >
              {busy ? "recording…" : "save override"}
            </button>
          </div>
          {error && (
            <p className="text-[11px] text-emperor">{error}</p>
          )}
          {overrides !== null && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-mono uppercase tracking-wide text-ink-mute dark:text-moonlight">
                Override history ({overrides.length})
              </p>
              {overrides.length === 0 && (
                <p className="text-[11px] text-ink-soft dark:text-starlight italic">
                  No overrides recorded for this chunk yet.
                </p>
              )}
              {overrides.map((o) => (
                <OverrideBadge
                  key={`${o.chunk_id}-${o.set_at ?? o.set_by ?? "?"}`}
                  override={o}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** One override badge — who changed this chunk's tier and why. */
function OverrideBadge({ override }: { override: TierOverride }) {
  return (
    <div className="border border-sun/40 rounded-md px-3 py-2 text-xs space-y-0.5 bg-sun/5">
      <div className="flex items-center gap-2 flex-wrap font-mono">
        <span className="text-ink dark:text-bright">
          {override.chunk_id}
        </span>
        <span className="text-ink-soft dark:text-starlight">
          tier {override.original_tier} → {override.override_tier}
        </span>
        {override.set_by && (
          <span className="text-shadow-1 dark:text-moonlight">set by {override.set_by}</span>
        )}
        {override.set_at && (
          <span className="text-[10px] text-ink-mute dark:text-moonlight">
            {new Date(override.set_at).toLocaleString()}
          </span>
        )}
      </div>
      <p className="text-ink-soft dark:text-starlight">{override.reason}</p>
    </div>
  );
}

function NodeCard({ node }: { node: ExplainNode }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 flex flex-col gap-1">
      <p className="text-sm text-ink dark:text-bright font-serif leading-snug">
        {node.canonical_label ?? node.node_id}
      </p>
      <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono uppercase tracking-wide">
        {node.node_type && (
          <span className="text-shadow-1 dark:text-moonlight">{node.node_type}</span>
        )}
        {node.graph_scope && (
          <span className="text-shadow-1 dark:text-moonlight">scope: {node.graph_scope}</span>
        )}
        <span className="text-ink-mute dark:text-moonlight">{node.node_id}</span>
      </div>
    </div>
  );
}

function EdgeRow({ edge }: { edge: ExplainEdge }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2 flex items-center gap-2 flex-wrap text-xs">
      <span className="font-mono text-ink dark:text-bright">{edge.relation}</span>
      <TierChip tier={edge.source_tier} />
      <ConfidenceChip confidence={edge.extraction_confidence} />
      {edge.document_id && (
        <Link
          to={`/read/${encodeURIComponent(edge.document_id)}`}
          className="font-mono text-[10px] text-ink-mute dark:text-moonlight hover:text-ink dark:hover:text-bright underline decoration-dotted underline-offset-2"
        >
          source →
        </Link>
      )}
      {edge.chunk_id && (
        <span className="font-mono text-[10px] text-ink-mute dark:text-moonlight">
          {edge.chunk_id}
        </span>
      )}
    </div>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
      {children}
    </h2>
  );
}

/** Resolve a document row for a chunk id; fall back to a minimal inline row
 *  so a missing document entry never strands the chunk's link. */
function documentFor(
  documentId: string,
  documents: ExplainDocument[],
): ExplainDocument {
  return (
    documents.find((d) => d.document_id === documentId) ?? {
      document_id: documentId,
      title: documentId,
      author: null,
      source_tier: 0,
      acquired_at: null,
    }
  );
}

function ChunksSection({
  chunks,
  documents,
  onTierChanged,
}: {
  chunks: ExplainChunk[];
  documents: ExplainDocument[];
  onTierChanged?: () => void;
}) {
  return (
    <section className="space-y-2">
      <SectionHeading>Source chunks ({chunks.length})</SectionHeading>
      {chunks.length === 0 && (
        <p className="text-sm text-shadow-1 dark:text-moonlight italic">
          No chunk excerpts are pinned.
        </p>
      )}
      <div className="space-y-3">
        {chunks.map((chunk) => (
          <ChunkBlock
            key={chunk.chunk_id}
            chunk={chunk}
            document={documentFor(chunk.document_id, documents)}
            onTierChanged={onTierChanged}
          />
        ))}
      </div>
    </section>
  );
}

function OverridesSection({ overrides }: { overrides: TierOverride[] }) {
  return (
    <section className="space-y-2">
      <SectionHeading>Tier overrides ({overrides.length})</SectionHeading>
      {overrides.length === 0 && (
        <p className="text-sm text-shadow-1 dark:text-moonlight italic">
          No chunk-tier overrides — every cited chunk still carries its
          ingested tier.
        </p>
      )}
      <div className="space-y-1.5">
        {overrides.map((o) => (
          <OverrideBadge key={`${o.chunk_id}-${o.set_at ?? o.set_by ?? "?"}`} override={o} />
        ))}
      </div>
    </section>
  );
}

/** Claim explain — the D1 wedge: node card + supporting edges + excerpts. */
function ClaimPanel({
  data,
  onTierChanged,
}: {
  data: ClaimExplainResponse;
  onTierChanged?: () => void;
}) {
  return (
    <div className="space-y-6">
      <NodeCard node={data.claim_node} />

      <section className="space-y-2">
        <SectionHeading>
          Supporting edges ({data.supporting_edges.length})
        </SectionHeading>
        {data.supporting_edges.length === 0 && (
          <p className="text-sm text-shadow-1 dark:text-moonlight italic">
            No supporting edges are recorded for this claim.
          </p>
        )}
        <div className="space-y-1.5">
          {data.supporting_edges.map((edge) => (
            <EdgeRow key={edge.edge_id} edge={edge} />
          ))}
        </div>
      </section>

      <ChunksSection
        chunks={data.chunks}
        documents={data.documents}
        onTierChanged={onTierChanged}
      />
      <OverridesSection overrides={data.chunk_tier_overrides} />
    </div>
  );
}

/** One manifest pin, resolved — rendered as its own compact card so the
 *  reader sees exactly what was pinned, per entity. */
function PinCard({
  pin,
  onTierChanged,
}: {
  pin: NodePin | EdgePin | ChunkPin | DocumentPin;
  onTierChanged?: () => void;
}) {
  const meta = (
    <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono uppercase tracking-wide">
      <span className="text-shadow-1 dark:text-moonlight">{pin.entity_kind}</span>
      <span className="text-ink-mute dark:text-moonlight">{pin.entity_id}</span>
      <span className="text-ink-mute dark:text-moonlight">
        pinned {new Date(pin.pinned_at).toLocaleString()}
      </span>
    </div>
  );

  if (pin.entity_kind === "node") {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 space-y-3">
        {meta}
        <NodeCard node={pin.claim_node} />
        {pin.supporting_edges.length > 0 && (
          <div className="space-y-1.5">
            {pin.supporting_edges.map((edge) => (
              <EdgeRow key={edge.edge_id} edge={edge} />
            ))}
          </div>
        )}
        <ChunksSection
          chunks={pin.chunks}
          documents={pin.documents}
          onTierChanged={onTierChanged}
        />
        <OverridesSection overrides={pin.chunk_tier_overrides} />
      </div>
    );
  }
  if (pin.entity_kind === "edge") {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 space-y-3">
        {meta}
        <EdgeRow edge={pin.edge} />
        <ChunksSection
          chunks={pin.chunks}
          documents={pin.documents}
          onTierChanged={onTierChanged}
        />
        <OverridesSection overrides={pin.chunk_tier_overrides} />
      </div>
    );
  }
  if (pin.entity_kind === "chunk") {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 space-y-3">
        {meta}
        <ChunkBlock
          chunk={pin.chunk}
          document={documentFor(pin.chunk.document_id, pin.documents)}
          onTierChanged={onTierChanged}
        />
        <OverridesSection overrides={pin.chunk_tier_overrides} />
      </div>
    );
  }
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 space-y-2">
      {meta}
      <DocumentLink document={pin.document} />
    </div>
  );
}

/** Synthesis explain — the manifest pins grouped by entity kind. */
function SynthesisPanel({
  data,
  onTierChanged,
}: {
  data: SynthesisExplainResponse;
  onTierChanged?: () => void;
}) {
  const groups: Array<{ kind: string; pins: SynthesisExplainResponse["pins"][keyof SynthesisExplainResponse["pins"]] }> = [
    { kind: "document", pins: data.pins.document },
    { kind: "chunk", pins: data.pins.chunk },
    { kind: "node", pins: data.pins.node },
    { kind: "edge", pins: data.pins.edge },
  ];
  return (
    <div className="space-y-6">
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2.5 flex flex-col gap-1">
        <p className="text-sm text-ink dark:text-bright font-serif leading-snug">
          Synthesis {data.synthesis_id}
        </p>
        <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono uppercase tracking-wide">
          <span className="text-ink-mute dark:text-moonlight">
            {new Date(data.generated_at).toLocaleString()}
          </span>
          <Link
            to={`/backtest/${encodeURIComponent(data.synthesis_id)}`}
            className="text-ink dark:text-bright hover:text-sun-deep dark:hover:text-sun underline decoration-dotted underline-offset-2"
          >
            backtest →
          </Link>
        </div>
      </div>

      {groups.map((group) => (
        <section key={group.kind} className="space-y-2">
          <SectionHeading>
            {group.kind} pins ({group.pins.length})
          </SectionHeading>
          {group.pins.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No {group.kind} pins were recorded.
            </p>
          )}
          <div className="space-y-3">
            {group.pins.map((pin) =>
              "unresolved" in pin && pin.unresolved ? (
                <div
                  key={`${pin.entity_kind}-${pin.entity_id}`}
                  className="border border-dashed border-red-300 dark:border-red-900 rounded-md px-3 py-2 text-xs space-y-0.5"
                >
                  <p className="font-mono text-emperor">
                    Unresolved pin — the manifest references a row that no
                    longer exists.
                  </p>
                  <p className="font-mono text-ink-soft dark:text-starlight">
                    {pin.entity_kind} · {pin.entity_id} · pinned{" "}
                    {new Date(pin.pinned_at).toLocaleString()}
                  </p>
                </div>
              ) : (
                <PinCard
                  key={`${pin.entity_kind}-${pin.entity_id}`}
                  pin={pin as NodePin | EdgePin | ChunkPin | DocumentPin}
                  onTierChanged={onTierChanged}
                />
              ),
            )}
          </div>
        </section>
      ))}
    </div>
  );
}

/** Document explain — reverse provenance: chunks → citing edges/nodes. */
function DocumentPanel({
  data,
  onTierChanged,
}: {
  data: DocumentExplainResponse;
  onTierChanged?: () => void;
}) {
  // Join citing edges to their source nodes (the claims that cite this doc).
  const byNode = new Map<string, ExplainNode>();
  for (const node of data.citing_nodes) byNode.set(node.node_id, node);
  const citing = data.citing_edges.map((edge) => ({
    edge,
    node: edge.source_node_id ? byNode.get(edge.source_node_id) ?? null : null,
  }));
  return (
    <div className="space-y-6">
      <DocumentLink document={data.document} />

      <section className="space-y-2">
        <SectionHeading>Chunks from this document ({data.chunks.length})</SectionHeading>
        {data.chunks.length === 0 && (
          <p className="text-sm text-shadow-1 dark:text-moonlight italic">
            No chunks are recorded for this document.
          </p>
        )}
        <div className="space-y-3">
          {data.chunks.map((chunk) => (
            <ChunkBlock
              key={chunk.chunk_id}
              chunk={chunk}
              document={data.document}
              onTierChanged={onTierChanged}
            />
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <SectionHeading>Claims that cite it ({citing.length})</SectionHeading>
        {citing.length === 0 && (
          <p className="text-sm text-shadow-1 dark:text-moonlight italic">
            No edges cite this document's chunks.
          </p>
        )}
        <div className="space-y-1.5">
          {citing.map(({ edge, node }) => (
            <div
              key={edge.edge_id}
              className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2 space-y-1"
            >
              <div className="flex items-center gap-2 flex-wrap text-xs">
                {node ? (
                  <Link
                    to={`/explain/claim/${encodeURIComponent(node.node_id)}`}
                    className="font-serif text-ink dark:text-bright hover:text-sun-deep dark:hover:text-sun underline decoration-dotted underline-offset-2"
                  >
                    {node.canonical_label ?? node.node_id}
                  </Link>
                ) : (
                  <span className="font-serif text-ink-soft dark:text-starlight">
                    {edge.source_node_id ?? "unknown node"}
                  </span>
                )}
                {edge.relation && (
                  <span className="font-mono text-shadow-1 dark:text-moonlight">
                    {edge.relation}
                  </span>
                )}
                <ConfidenceChip confidence={edge.extraction_confidence} />
              </div>
              <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
                {edge.edge_id}
                {edge.chunk_id ? ` · ${edge.chunk_id}` : ""}
              </p>
            </div>
          ))}
        </div>
      </section>

      <OverridesSection overrides={data.chunk_tier_overrides} />
    </div>
  );
}

export function Explain() {
  const { kind: rawKind, id } = useParams<{ kind: string; id: string }>();
  const kind: ExplainKind | null =
    rawKind === "claim" || rawKind === "synthesis" || rawKind === "document"
      ? rawKind
      : null;
  // P0 §5: audit-only served-impression record for this provenance render.
  useServedImpression({
    surface: "explain",
    itemKind: kind ?? "unknown",
    itemId: id ?? "",
  });

  const [data, setData] = useState<
    ClaimExplainResponse | SynthesisExplainResponse | DocumentExplainResponse | null
  >(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    if (!kind || !id) {
      setLoading(false);
      return;
    }
    try {
      if (kind === "claim") {
        setData(await explainClaim(id));
      } else if (kind === "synthesis") {
        setData(await explainSynthesis(id));
      } else {
        setData(await explainDocument(id));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [kind, id]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const meta = kind ? KIND_META[kind] : null;
  const generatedAt =
    data && "generated_at" in data ? data.generated_at : null;

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              {meta ? meta.title : "Explain"}
            </h1>
            {meta && (
              <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                {meta.lede}
              </p>
            )}
            {id && (
              <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
                {kind ? `${kind} · ${id}` : id}
                {generatedAt ? ` · generated ${new Date(generatedAt).toLocaleString()}` : ""}
              </p>
            )}
          </header>

          {!kind && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              Unknown explain kind — expected /explain/claim/:id,
              /explain/synthesis/:id, or /explain/document/:id.
            </p>
          )}

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {data && kind === "claim" && (
            <ClaimPanel data={data as ClaimExplainResponse} onTierChanged={reload} />
          )}
          {data && kind === "synthesis" && (
            <SynthesisPanel
              data={data as SynthesisExplainResponse}
              onTierChanged={reload}
            />
          )}
          {data && kind === "document" && (
            <DocumentPanel
              data={data as DocumentExplainResponse}
              onTierChanged={reload}
            />
          )}
        </div>
      </main>
    </div>
  );
}

export default Explain;
