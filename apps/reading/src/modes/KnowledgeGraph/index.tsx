import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { exploreGraph } from "../../api/graph";
import type {
  GraphEdge,
  GraphExploreResponse,
  GraphNode,
} from "../../api/graph";

const NODE_TYPES = ["", "insight", "question", "claim", "mechanism", "entity"];
const SCOPES = ["", "depth", "cross_domain", "constraint"];

export default function KnowledgeGraph() {
  const [query, setQuery] = useState("");
  const [nodeType, setNodeType] = useState("");
  const [scope, setScope] = useState("");
  const [investigationId, setInvestigationId] = useState("");
  const [result, setResult] = useState<GraphExploreResponse | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadGeneration = useRef(0);

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setBusy(true);
    setError(null);
    try {
      const next = await exploreGraph({
        query,
        nodeType,
        graphScope: scope,
        investigationId,
      });
      if (generation !== loadGeneration.current) return;
      setResult(next);
      setSelectedNodeId((current) =>
        next.nodes.some((node) => node.node_id === current)
          ? current
          : (next.nodes[0]?.node_id ?? null),
      );
      setSelectedEdgeId(null);
    } catch (reason) {
      if (generation !== loadGeneration.current) return;
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (generation === loadGeneration.current) setBusy(false);
    }
  }, [investigationId, nodeType, query, scope]);

  useEffect(() => {
    void load();
    // Initial graph inventory only. Filters run on the explicit Explore action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedNode = useMemo(
    () => result?.nodes.find((node) => node.node_id === selectedNodeId) ?? null,
    [result?.nodes, selectedNodeId],
  );
  const adjacentEdges = useMemo(
    () =>
      (result?.edges || []).filter(
        (edge) =>
          edge.source_node_id === selectedNodeId || edge.target_node_id === selectedNodeId,
      ),
    [result?.edges, selectedNodeId],
  );
  const selectedEdge =
    adjacentEdges.find((edge) => edge.edge_id === selectedEdgeId) ??
    adjacentEdges[0] ??
    null;

  return (
    <main
      className="min-h-screen bg-ice-0 text-ink dark:bg-charcoal-2 dark:text-bright"
      data-testid="knowledge-graph"
      data-view-format="html"
      data-read-only="true"
    >
      <header className="border-b border-rule px-5 py-5 dark:border-charcoal-1 lg:px-8">
        <div className="mx-auto flex max-w-[1500px] flex-col gap-5">
          <div className="flex flex-col justify-between gap-3 md:flex-row md:items-end">
            <div className="max-w-2xl">
              <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-shadow-1 dark:text-moonlight">
                Substrate cartography · read-only
              </p>
              <h1 className="mt-1 font-serif text-3xl leading-tight md:text-4xl">
                Follow an idea to its receipts.
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-soft dark:text-starlight">
                Search the accumulated graph, inspect exact relationships, then walk the stored evidence back to its chunk and source.
              </p>
            </div>
            <div className="font-mono text-[11px] text-shadow-1 dark:text-moonlight" data-testid="graph-counts">
              {result ? `${result.node_count} nodes · ${result.edge_count} adjacent edges` : "Reading graph…"}
              {result?.truncated ? " · bounded result" : ""}
            </div>
          </div>

          <form
            className="grid gap-2 md:grid-cols-[minmax(16rem,1fr)_10rem_10rem_minmax(12rem,0.7fr)_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void load();
            }}
          >
            <input
              aria-label="Search graph"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search labels or paste a node id"
              className="rounded-md border border-rule bg-transparent px-3 py-2 text-sm outline-none focus:border-aurora dark:border-charcoal-1"
            />
            <select aria-label="Node type" value={nodeType} onChange={(event) => setNodeType(event.target.value)} className="rounded-md border border-rule bg-ice-0 px-2 py-2 text-xs dark:border-charcoal-1 dark:bg-charcoal-2">
              {NODE_TYPES.map((value) => <option key={value || "all"} value={value}>{value || "all node types"}</option>)}
            </select>
            <select aria-label="Graph scope" value={scope} onChange={(event) => setScope(event.target.value)} className="rounded-md border border-rule bg-ice-0 px-2 py-2 text-xs dark:border-charcoal-1 dark:bg-charcoal-2">
              {SCOPES.map((value) => <option key={value || "all"} value={value}>{value || "all scopes"}</option>)}
            </select>
            <input aria-label="Investigation id" value={investigationId} onChange={(event) => setInvestigationId(event.target.value)} placeholder="Investigation id" className="rounded-md border border-rule bg-transparent px-3 py-2 text-xs outline-none focus:border-aurora dark:border-charcoal-1" />
            <button type="submit" disabled={busy} className="rounded-md bg-ink px-4 py-2 font-mono text-xs text-white hover:bg-shadow-2 disabled:opacity-50 dark:bg-bright dark:text-charcoal-2">
              {busy ? "Tracing…" : "Explore"}
            </button>
          </form>
          {error ? <p className="text-sm text-emperor" role="alert">{error}</p> : null}
        </div>
      </header>

      <div className="mx-auto grid max-w-[1500px] grid-cols-1 lg:grid-cols-[minmax(17rem,0.8fr)_minmax(21rem,1fr)_minmax(20rem,1.05fr)]">
        <section className="min-h-[28rem] border-b border-rule p-4 dark:border-charcoal-1 lg:border-b-0 lg:border-r lg:p-5" aria-label="Graph nodes">
          <PanelHeading eyebrow="Node ledger" title="Ideas in scope" />
          {result && result.nodes.length === 0 ? (
            <EmptyState>Nothing in the graph matches these filters. Broaden the label, type, or investigation.</EmptyState>
          ) : (
            <ol className="mt-4 space-y-1" data-testid="graph-node-list">
              {(result?.nodes || []).map((node) => (
                <NodeRow key={node.node_id} node={node} active={node.node_id === selectedNodeId} onSelect={() => { setSelectedNodeId(node.node_id); setSelectedEdgeId(null); }} />
              ))}
            </ol>
          )}
        </section>

        <section className="min-h-[28rem] border-b border-rule p-4 dark:border-charcoal-1 lg:border-b-0 lg:border-r lg:p-5" aria-label="Relationships">
          <PanelHeading eyebrow="Relationship path" title={selectedNode?.label || "Select an idea"} />
          {selectedNode ? (
            <div className="mt-3 flex flex-wrap gap-2 font-mono text-[10px] text-shadow-1 dark:text-moonlight">
              <span>{selectedNode.node_type}</span><span>scope:{selectedNode.graph_scope}</span><span>degree:{selectedNode.degree}</span>
            </div>
          ) : null}
          {selectedNode && adjacentEdges.length === 0 ? <EmptyState>No stored relationships touch this node. Antiek will not invent a path.</EmptyState> : null}
          <ol className="mt-5 space-y-3" data-testid="graph-edge-list">
            {adjacentEdges.map((edge) => (
              <EdgeRow key={edge.edge_id} edge={edge} active={edge.edge_id === selectedEdge?.edge_id} onSelect={() => setSelectedEdgeId(edge.edge_id)} />
            ))}
          </ol>
        </section>

        <section className="min-h-[28rem] p-4 lg:p-5" aria-label="Evidence folio">
          <PanelHeading eyebrow="Provenance folio" title="What supports this edge" />
          {selectedEdge ? <EvidenceRail edge={selectedEdge} /> : <EmptyState>Select a relationship to inspect its stored evidence.</EmptyState>}
        </section>
      </div>
    </main>
  );
}

function PanelHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <header className="min-w-0"><p className="font-mono text-[10px] uppercase tracking-[0.18em] text-shadow-1 dark:text-moonlight">{eyebrow}</p><h2 className="mt-1 break-words font-serif text-xl leading-snug">{title}</h2></header>;
}

function EmptyState({ children }: { children: ReactNode }) {
  return <p className="mt-6 border-l-2 border-rule pl-3 text-sm leading-relaxed text-shadow-1 dark:border-charcoal-1 dark:text-moonlight">{children}</p>;
}

function NodeRow({ node, active, onSelect }: { node: GraphNode; active: boolean; onSelect: () => void }) {
  return <li className="min-w-0"><button type="button" onClick={onSelect} data-testid={`graph-node-${node.node_id}`} className={`w-full min-w-0 rounded-md border px-3 py-2 text-left transition-colors ${active ? "border-aurora bg-aurora/10" : "border-transparent hover:border-rule hover:bg-ice-1 dark:hover:border-charcoal-1 dark:hover:bg-charcoal-1"}`}><span className="block break-words font-serif text-sm leading-snug">{node.label}</span><span className="mt-1 flex min-w-0 flex-wrap justify-between gap-1 break-all font-mono text-[10px] text-shadow-1 dark:text-moonlight"><span>{node.node_type} · {node.graph_scope}</span><span>d{node.degree}</span></span></button></li>;
}

function EdgeRow({ edge, active, onSelect }: { edge: GraphEdge; active: boolean; onSelect: () => void }) {
  return <li className="min-w-0"><button type="button" onClick={onSelect} data-testid={`graph-edge-${edge.edge_id}`} className={`w-full min-w-0 rounded-md border p-3 text-left ${active ? "border-sun bg-sun/10" : "border-rule hover:border-sun dark:border-charcoal-1"}`}><span className="block break-words font-serif text-sm">{edge.source_label}</span><span className="my-2 flex min-w-0 items-center gap-2 break-all font-mono text-[10px] uppercase tracking-[0.12em] text-shadow-1 dark:text-moonlight"><span className="h-px min-w-4 flex-1 bg-rule dark:bg-charcoal-1" />{edge.relation}<span className="h-px min-w-4 flex-1 bg-rule dark:bg-charcoal-1" /></span><span className="block break-words font-serif text-sm">{edge.target_label}</span><span className="mt-2 block break-all font-mono text-[10px] text-shadow-1 dark:text-moonlight">confidence {Math.round(edge.confidence * 100)}%{edge.investigation_id ? ` · ${edge.investigation_id}` : ""}</span></button></li>;
}

function EvidenceRail({ edge }: { edge: GraphEdge }) {
  const evidence = edge.evidence;
  return <div className="relative mt-5 space-y-5 pl-7 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-sun before:content-['']" data-testid="graph-evidence-rail">
    <EvidenceStop label="Relationship" value={`${edge.relation} · ${Math.round(edge.confidence * 100)}% confidence`} />
    <EvidenceStop label="Origin" value={edge.investigation_id ? "Recorded research" : "No originating research recorded"} detail={edge.investigation_id ? "Reopen the research that produced this relationship, then use its existing challenge and chase tools to continue." : "This relationship has no investigation provenance. Antiek will not invent a continuation target."} />
    <EvidenceStop label="Chunk" value={evidence.chunk_id || "No chunk recorded"} detail={evidence.chunk_text || "This edge has no stored passage. Treat it as ungrounded until evidence is attached."} />
    <EvidenceStop label="Document" value={evidence.source_title || evidence.source_document_id || "No source document recorded"} detail={[evidence.source_author, evidence.section_path].filter(Boolean).join(" · ")} />
    <EvidenceStop label="Rights" value={`tier ${evidence.source_tier} · ${evidence.content_class || "unknown"}`} detail={evidence.servable ? "Servable in portable output." : "Private or rights-restricted. Keep full text inside the workstation."} tone={evidence.servable ? "safe" : "warn"} />
    <div className="flex flex-wrap gap-x-4 gap-y-2">
      {edge.investigation_id ? <a data-testid="graph-open-originating-research" href={`/inv/${encodeURIComponent(edge.investigation_id)}`} className="inline-block font-mono text-[11px] underline decoration-sun decoration-2 underline-offset-4 hover:text-aurora">Open originating research</a> : null}
      {evidence.source_document_id ? <a href={`/documents?document_id=${encodeURIComponent(evidence.source_document_id)}`} className="inline-block font-mono text-[11px] underline underline-offset-4 hover:text-aurora">Open source record</a> : null}
    </div>
  </div>;
}

function EvidenceStop({ label, value, detail, tone }: { label: string; value: string; detail?: string; tone?: "safe" | "warn" }) {
  return <div className="relative min-w-0"><span className={`absolute -left-7 top-1 h-[15px] w-[15px] rounded-full border-2 bg-ice-0 dark:bg-charcoal-2 ${tone === "warn" ? "border-emperor" : tone === "safe" ? "border-aurora" : "border-sun"}`} /><p className="font-mono text-[10px] uppercase tracking-[0.16em] text-shadow-1 dark:text-moonlight">{label}</p><p className="mt-1 break-words font-serif text-sm leading-snug">{value}</p>{detail ? <p className="mt-1 break-words text-xs leading-relaxed text-ink-soft dark:text-starlight">{detail}</p> : null}</div>;
}
