// SPR-10 / M5 — Share-with-annotations bundle client.
//
// The Python backend ships a streaming zip from
// ``POST /api/library/share-bundle`` containing:
//   - <title>.pdf       — the parent PDF bytes
//   - <title>.antiek    — the sidecar with the user's highlights /
//                         voice anchors / user-asserted edges
//
// The recipient drops the zip into the library; SPR-10/M4's
// ingest-time sidecar detection (services/ingestion/sidecar_detector)
// picks up the pair, ingests the PDF, and applies the sidecar after
// the substrate write completes. From the recipient's perspective,
// the operator's annotations appear flagged as "imported from share".
//
// Why a wrapper rather than fetch() inline at the call site:
// same polyglot-seam discipline as ingest.ts — the contract lives in
// one place. The endpoint shape may change (e.g., streaming-zip vs.
// pre-built bytes); the call site stays stable.

/** Base URL for the substrate API. Same resolver as ingest.ts. */
function apiBase(): string {
  const env = (import.meta as { env?: { VITE_ANTIEK_API_BASE?: string } }).env;
  return (env?.VITE_ANTIEK_API_BASE || "").replace(/\/+$/, "");
}

/** Request shape for ``POST /api/library/share-bundle``. */
export interface ShareBundleRequest {
  document_id: string;
  user_id: string;
  /** Optional override for the filename written into the zip. The
   *  backend defaults to the document title (slugified) or
   *  ``document_id`` if no title exists. */
  filename_hint?: string;
}

/** Response shape — informational fields the UI may render. The
 *  actual download lives in the streamed body. */
export interface ShareBundleMetadata {
  bundle_filename: string;       // "<title>.zip"
  pdf_filename: string;          // "<title>.pdf"
  sidecar_filename: string;      // "<title>.antiek"
  bytes: number;                 // total bundle size
  highlights_included: number;
  voice_notes_included: number;
  user_asserted_edges_included: number;
  signature_pubkey: string;      // user's Ed25519 public key (base64)
}

/**
 * Build and download the share bundle for one document.
 *
 * Behavior: POSTs the request, reads the streamed zip body, and
 * triggers a browser download via a transient anchor element. The
 * promise resolves to the bundle metadata once the download has
 * been handed off to the browser.
 *
 * The caller is responsible for revoking the object URL after the
 * user finishes saving — we return the URL alongside the metadata
 * so callers can clean up explicitly.
 */
export async function downloadShareBundle(
  body: ShareBundleRequest,
  init?: RequestInit,
): Promise<{ metadata: ShareBundleMetadata; objectUrl: string }> {
  const url = `${apiBase()}/api/library/share-bundle`;
  const res = await fetch(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include", // ANTIEK_SESSION cookie
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ShareBundleError(
      res.status,
      (detail as { error?: { code?: string } })?.error?.code || `http_${res.status}`,
      detail,
    );
  }

  // The backend pins metadata into response headers so we can render
  // a confirmation without parsing the zip on the client. (We do NOT
  // peek into the zip in JS — the bytes are an opaque artifact for
  // download.)
  const metadata: ShareBundleMetadata = {
    bundle_filename: res.headers.get("X-Antiek-Bundle-Filename") || "annotations.zip",
    pdf_filename: res.headers.get("X-Antiek-Pdf-Filename") || "document.pdf",
    sidecar_filename: res.headers.get("X-Antiek-Sidecar-Filename") || "document.antiek",
    bytes: parseInt(res.headers.get("Content-Length") || "0", 10),
    highlights_included: parseInt(res.headers.get("X-Antiek-Highlights-Count") || "0", 10),
    voice_notes_included: parseInt(res.headers.get("X-Antiek-Voicenotes-Count") || "0", 10),
    user_asserted_edges_included: parseInt(res.headers.get("X-Antiek-Edges-Count") || "0", 10),
    signature_pubkey: res.headers.get("X-Antiek-Signing-Pubkey") || "",
  };

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);

  // Trigger the browser download. We do this here (rather than in
  // the component) so the call site is one line: "share = await
  // downloadShareBundle({...})".
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = metadata.bundle_filename;
  document.body.appendChild(a);
  a.click();
  a.remove();

  return { metadata, objectUrl };
}

/** Typed error thrown by share-bundle methods. */
export class ShareBundleError extends Error {
  status: number;
  code: string;
  detail: unknown;
  constructor(status: number, code: string, detail: unknown) {
    super(`share-bundle failed: ${code} (HTTP ${status})`);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}
