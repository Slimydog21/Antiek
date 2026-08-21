export interface ArtifactFeedbackSelection {
  normalization: "unicode-nfc-v1";
  node_id: string;
  source_document_id: string | null;
  node_text_sha256: string;
  start_scalar: number;
  end_scalar: number;
  quote: string;
  prefix: string;
  suffix: string;
}

function semanticNode(node: Node): HTMLElement | null {
  const element = node instanceof HTMLElement ? node : node.parentElement;
  return element?.closest<HTMLElement>("[data-antiek-node-id]") ?? null;
}

function textBefore(node: HTMLElement, container: Node, offset: number): string {
  const range = node.ownerDocument.createRange();
  range.selectNodeContents(node);
  range.setEnd(container, offset);
  return range.toString();
}

function scalarLength(value: string): number {
  return Array.from(value).length;
}

function scalarSlice(value: string, start: number, end?: number): string {
  return Array.from(value).slice(start, end).join("");
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function anchorFromRange(
  range: Range,
): Promise<ArtifactFeedbackSelection | null> {
  if (range.collapsed) return null;
  const startNode = semanticNode(range.startContainer);
  const endNode = semanticNode(range.endContainer);
  if (!startNode || startNode !== endNode) return null;
  const nodeId = startNode.dataset.antiekNodeId;
  if (!nodeId) return null;

  const normalizedText = (startNode.textContent ?? "").normalize("NFC");
  const normalizedBeforeStart = textBefore(
    startNode,
    range.startContainer,
    range.startOffset,
  ).normalize("NFC");
  const normalizedBeforeEnd = textBefore(
    startNode,
    range.endContainer,
    range.endOffset,
  ).normalize("NFC");
  const startScalar = scalarLength(normalizedBeforeStart);
  const endScalar = scalarLength(normalizedBeforeEnd);
  if (endScalar <= startScalar) return null;
  const quote = scalarSlice(normalizedText, startScalar, endScalar);
  if (!quote.trim()) return null;

  return {
    normalization: "unicode-nfc-v1",
    node_id: nodeId,
    source_document_id: startNode.dataset.antiekSourceDocumentId ?? null,
    node_text_sha256: await sha256(normalizedText),
    start_scalar: startScalar,
    end_scalar: endScalar,
    quote,
    prefix: scalarSlice(normalizedText, Math.max(0, startScalar - 32), startScalar),
    suffix: scalarSlice(normalizedText, endScalar, endScalar + 32),
  };
}
