import { API_BASE, apiFetch } from "../lib/api";

export type GraphNode = {
  node_id: string;
  label: string;
  node_type: string;
  graph_scope: string;
  degree: number;
  created_at: string;
};

export type GraphEvidence = {
  chunk_id?: string | null;
  chunk_text?: string | null;
  section_path?: string | null;
  source_document_id?: string | null;
  source_title?: string | null;
  source_author?: string | null;
  source_tier: number;
  content_class?: string | null;
  ip_holder_id?: string | null;
  servable: boolean;
};

export type GraphEdge = {
  edge_id: string;
  source_node_id: string;
  source_label: string;
  target_node_id: string;
  target_label: string;
  relation: string;
  graph_scope: string;
  investigation_id?: string | null;
  confidence: number;
  valid_from: string;
  valid_until?: string | null;
  evidence: GraphEvidence;
};

export type GraphExploreResponse = {
  query: string;
  node_type?: string | null;
  graph_scope?: string | null;
  investigation_id?: string | null;
  node_count: number;
  edge_count: number;
  truncated: boolean;
  read_only: true;
  view_format: "html";
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export async function exploreGraph(options: {
  query?: string;
  nodeType?: string;
  graphScope?: string;
  investigationId?: string;
  limit?: number;
} = {}): Promise<GraphExploreResponse> {
  const params = new URLSearchParams();
  if (options.query?.trim()) params.set("q", options.query.trim());
  if (options.nodeType?.trim()) params.set("node_type", options.nodeType.trim());
  if (options.graphScope?.trim()) params.set("graph_scope", options.graphScope.trim());
  if (options.investigationId?.trim()) {
    params.set("investigation_id", options.investigationId.trim());
  }
  params.set("limit", String(options.limit ?? 60));
  const response = await apiFetch(`${API_BASE}/graph/explore?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Knowledge graph query failed: HTTP ${response.status}`);
  }
  return (await response.json()) as GraphExploreResponse;
}
