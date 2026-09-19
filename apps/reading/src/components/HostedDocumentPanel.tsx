import { useEffect, useState } from "react";

import { fetchHostedDocument, type HostedDocumentReceipt } from "../api/hostedDocuments";
import HostedHtmlDocumentHost from "./windows/HostedHtmlDocumentHost";
import { useAuth } from "../lib/auth";

export function resolveCitationAnchors(
  requested: readonly string[],
  received: HostedDocumentReceipt["chunk_anchors"],
): string[] {
  if (!requested.length) return [];
  if (!received || received.length !== requested.length) return [];
  const anchors: string[] = [];
  for (let index = 0; index < requested.length; index += 1) {
    const item = received[index];
    if (
      !item
      || item.chunk_id !== requested[index]
      || !/^antiek-chunk-[a-f0-9]{64}$/.test(item.anchor_id)
      || anchors.includes(item.anchor_id)
    ) return [];
    anchors.push(item.anchor_id);
  }
  return anchors;
}

/** Panel-native canonical document loader. Source page is provenance only. */
export default function HostedDocumentPanel(props: {
  documentId?: string;
  document_id?: string;
  id?: string;
  initialPage?: number;
  citationChunkIds?: string[];
  citationReceiptSha256?: string;
}) {
  const { sessionGeneration } = useAuth();
  const documentId = (props.document_id || props.documentId || props.id || "").trim();
  const [receipt, setReceipt] = useState<HostedDocumentReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedIdentity, setLoadedIdentity] = useState("");
  const requestedChunks = Array.isArray(props.citationChunkIds) ? props.citationChunkIds : [];
  const requestIdentity = `${sessionGeneration}:${documentId}:${JSON.stringify(requestedChunks)}`;

  useEffect(() => {
    let active = true;
    setReceipt(null);
    setError(null);
    setLoadedIdentity("");
    if (!documentId) {
      setError("Canonical document_id is required.");
      setLoadedIdentity(requestIdentity);
      return () => { active = false; };
    }
    void (async () => {
      try {
        const value = await fetchHostedDocument(documentId, requestedChunks);
        if (!active) return;
        if (value.document_id !== documentId) {
          setError("Canonical document identity does not match the requested document_id.");
          setLoadedIdentity(requestIdentity);
          return;
        }
        if (value.view_format !== "html" || value.state !== "ready" || !value.html?.trim()) {
          setError(value.non_viewable_reason || "Canonical HTML is not viewable.");
          setLoadedIdentity(requestIdentity);
          return;
        }
        setReceipt(value);
        setLoadedIdentity(requestIdentity);
      } catch (reason: unknown) {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason));
          setLoadedIdentity(requestIdentity);
        }
      }
    })();
    return () => { active = false; };
  }, [documentId, props.citationChunkIds, sessionGeneration]);

  if (loadedIdentity === requestIdentity && error) return <p role="alert" className="p-4 text-xs font-mono text-emperor">{error}</p>;
  if (loadedIdentity !== requestIdentity || !receipt) return <p role="status" className="p-4 text-xs font-mono">Loading canonical HTML…</p>;
  const citationAnchors = resolveCitationAnchors(
    props.citationChunkIds ?? [],
    receipt.chunk_anchors,
  );
  return (
    <div data-testid="hosted-document-panel" data-document-id={receipt.document_id} data-view-format="html" data-source-page={props.initialPage ?? ""}>
      <HostedHtmlDocumentHost
        document_id={receipt.document_id}
        title={receipt.title}
        html={receipt.html ?? ""}
        view_format="html"
        owner_id={receipt.owner_id}
        source="workspace_hosted_document"
        initial_anchor_id={citationAnchors[0]}
        citation_anchor_ids={citationAnchors}
        citation_receipt_sha256={props.citationReceiptSha256}
      />
    </div>
  );
}
