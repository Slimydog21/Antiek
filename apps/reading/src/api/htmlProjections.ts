import { API_BASE, apiFetch } from "../lib/api";

const MAX_HTML_LENGTH = 25 * 1024 * 1024;
const MAX_RESPONSE_LENGTH = 50 * 1024 * 1024;
const MAX_MAPPINGS = 100_000;
const MAX_IDENTITY_FIELDS = 16;
const MAX_STRING_LENGTH = 2048;
const SHA256 = /^[0-9a-f]{64}$/;
const SAFE_ID = /^[A-Za-z][A-Za-z0-9._:-]{0,255}$/;
const IDENTITY_FIELDS = ["source_asset_id", "source_document_id", "source_sha256", "converter_id", "converter_version", "sanitizer_policy", "sanitizer_version"] as const;

export interface HtmlProjectionAnchorMapping {
  source_locator: Readonly<Record<string, string | number>>;
  state: "resolved";
  html_anchor_id: string;
  candidates: readonly [];
}

export interface HtmlProjection {
  identity: Readonly<Record<string, string>>;
  projection_id: string;
  html_sha256: string;
  html: string;
  anchor_mappings: readonly HtmlProjectionAnchorMapping[];
}

export class HtmlProjectionError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(detail || `HTML projection request failed (HTTP ${status})`);
    this.name = "HtmlProjectionError";
  }
}

const record = (value: unknown): Record<string, unknown> | null =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>) : null;

function boundedString(value: unknown, max = MAX_STRING_LENGTH): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function parseProjection(value: unknown, requestedDocumentId: string): HtmlProjection {
  const root = record(value);
  if (!root) throw new Error("Invalid HTML projection response");
  const identityValue = record(root.identity);
  if (!identityValue || Object.keys(identityValue).length !== IDENTITY_FIELDS.length || Object.keys(identityValue).length > MAX_IDENTITY_FIELDS)
    throw new Error("Invalid HTML projection identity");
  const identity: Record<string, string> = {};
  for (const [key, item] of Object.entries(identityValue)) {
    if (!(IDENTITY_FIELDS as readonly string[]).includes(key) || !boundedString(item)) throw new Error("Invalid HTML projection identity");
    identity[key] = item;
  }
  if (identity.source_document_id !== requestedDocumentId || !SHA256.test(identity.source_sha256)) throw new Error("Invalid HTML projection identity");
  if (typeof root.projection_id !== "string" || !/^hproj-[0-9a-f]{64}$/.test(root.projection_id)) throw new Error("Invalid HTML projection id");
  if (typeof root.html_sha256 !== "string" || !SHA256.test(root.html_sha256)) throw new Error("Invalid HTML projection hash");
  if (typeof root.html !== "string" || root.html.length > MAX_HTML_LENGTH) throw new Error("Invalid HTML projection HTML");
  if (!Array.isArray(root.anchor_mappings) || root.anchor_mappings.length > MAX_MAPPINGS) throw new Error("Invalid HTML projection anchors");
  const anchor_mappings = root.anchor_mappings.map((item): HtmlProjectionAnchorMapping => {
    const mapping = record(item);
    const locator = mapping && record(mapping.source_locator);
    if (!mapping || !locator || Object.keys(locator).length > 8 || mapping.state !== "resolved" ||
        !boundedString(mapping.html_anchor_id, 256) || !SAFE_ID.test(mapping.html_anchor_id) ||
        !Array.isArray(mapping.candidates) || mapping.candidates.length !== 0)
      throw new Error("Invalid HTML projection anchor mapping");
    const source_locator: Record<string, string | number> = {};
    for (const [key, locatorValue] of Object.entries(locator)) {
      if (!boundedString(key, 64) || !((typeof locatorValue === "string" && locatorValue.length <= MAX_STRING_LENGTH) ||
          (typeof locatorValue === "number" && Number.isSafeInteger(locatorValue))))
        throw new Error("Invalid HTML projection source locator");
      source_locator[key] = locatorValue;
    }
    return { source_locator, state: "resolved", html_anchor_id: mapping.html_anchor_id, candidates: [] };
  });
  return { identity, projection_id: root.projection_id, html_sha256: root.html_sha256, html: root.html, anchor_mappings };
}

function errorDetail(body: string): string {
  if (body.length > 4096) return "";
  try {
    const parsed = record(JSON.parse(body));
    return parsed && boundedString(parsed.detail, 1000) ? parsed.detail : "";
  } catch { return ""; }
}

export async function getHtmlProjectionByDocument(documentId: string, signal?: AbortSignal): Promise<HtmlProjection> {
  const response = await apiFetch(`${API_BASE}/html-projections/by-document/${encodeURIComponent(documentId)}`, { signal });
  if (!response.ok) throw new HtmlProjectionError(response.status, errorDetail(await response.text()));
  const body = await response.text();
  if (body.length > MAX_RESPONSE_LENGTH) throw new Error("Invalid HTML projection response");
  try {
    return parseProjection(JSON.parse(body), documentId);
  } catch (error) {
    if (error instanceof SyntaxError) throw new Error("Invalid HTML projection response");
    throw error;
  }
}
