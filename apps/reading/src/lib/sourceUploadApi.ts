import { API_BASE, apiFetch } from "./api";

export const SOURCE_UPLOAD_MAX_BYTES = 64 * 1024 * 1024;
export const SOURCE_UPLOAD_MAX_LABEL = "64 MiB";

export const SOURCE_UPLOAD_EXTENSIONS = [
  ".pdf", ".html", ".htm", ".md", ".markdown", ".txt", ".text",
  ".doc", ".docx", ".docm", ".ppt", ".pps", ".pot", ".pptx",
  ".pptm", ".ppsx", ".ppsm", ".xlsx", ".xls", ".xlsm", ".xlsb",
  ".odt", ".ods", ".odp", ".rtf", ".csv",
] as const;

/* Privacy gate for authored uploads (A-06 client half; backend INBOX
 * 2026-09-27T00:40Z). The legacy authored token is never sent: on an API
 * without A-06 it mints a publicly served class (substrate/books/servability.py
 * maps it to platform_authored). The private token is sent only when the API
 * advertised it, and that is enforced here, not by callers:
 *
 *   - loadUploadAttestations() is the only source of an
 *     UploadAttestationCapability (frozen, recorded in a module WeakSet);
 *   - attestationToken("authored", cap) issues a VerifiedAuthoredAttestation
 *     (an opaque object, recorded in a module WeakSet) only for such a
 *     capability that lists the private token;
 *   - uploadSource() accepts "personal_reading" or an issued attestation and
 *     nothing else. A raw string is a type error and a runtime
 *     SourceUploadError("authored_unavailable"), before any request.
 *
 * The raw private token is deliberately not exported. */
const AUTHORED_PRIVATE_TOKEN = "user_authored_private";

declare const capabilityBrand: unique symbol;
declare const authoredBrand: unique symbol;

/** GET /sources/upload/attestations (static; served by an A-06-capable API).
 * Obtainable only from loadUploadAttestations(); frozen. */
export interface UploadAttestationCapability {
  readonly accepted: readonly string[];
  readonly authored_default: string | null;
  readonly aliases: Readonly<Record<string, string>>;
  readonly [capabilityBrand]: true;
}

/** Proof that the user chose "authored" against a verified capability that
 * lists the private token. Opaque; issued only by attestationToken(). */
export interface VerifiedAuthoredAttestation {
  readonly [authoredBrand]: true;
}

/** What uploadSource() accepts. */
export type AcquisitionAttestation = "personal_reading" | VerifiedAuthoredAttestation;

/** What the user chose in the form; mapped by attestationToken. */
export type AttestationChoice = "personal" | "authored";

const verifiedCapabilities = new WeakSet<object>();
const issuedAuthoredAttestations = new WeakSet<object>();

/** The wire token for an attestation, or authored_unavailable. */
function wireAttestation(attestation: unknown): string {
  if (attestation === "personal_reading") return "personal_reading";
  if (
    typeof attestation === "object" &&
    attestation !== null &&
    issuedAuthoredAttestations.has(attestation)
  ) {
    return AUTHORED_PRIVATE_TOKEN;
  }
  throw new SourceUploadError("authored_unavailable");
}

export interface SourceUploadResponse {
  document_id: string;
  detected_kind: string;
  reader_html_available: boolean;
  chunk_count: number;
  /** The rights class in effect after the call (a re-upload reports the stored one). */
  content_class: string;
}

export type SourceUploadErrorCode =
  | "too_large"
  | "unsupported"
  | "book_ceremony"
  | "attestation_conflict"
  | "authored_unavailable"
  | "conversion_failed"
  | "cancelled"
  | "unavailable";

export class SourceUploadError extends Error {
  constructor(public readonly code: SourceUploadErrorCode) {
    super(code);
    this.name = "SourceUploadError";
  }
}

export function validateSourceUpload(file: File): SourceUploadErrorCode | null {
  if (file.size > SOURCE_UPLOAD_MAX_BYTES) return "too_large";
  const lower = file.name.toLowerCase();
  return SOURCE_UPLOAD_EXTENSIONS.some((extension) => lower.endsWith(extension))
    ? null
    : "unsupported";
}

function codeForStatus(status: number): SourceUploadErrorCode {
  if (status === 413) return "too_large";
  if (status === 415) return "unsupported";
  if (status === 409) return "book_ceremony";
  if (status === 422) return "conversion_failed";
  return "unavailable";
}

/** True only when the API lists the private authored token. `authored_default`
 * and `aliases` are deliberately ignored: they are advisory, and following an
 * alias could lead back to the legacy public class. */
export function authoredUploadSupported(capability: UploadAttestationCapability | null): boolean {
  return (
    capability !== null &&
    verifiedCapabilities.has(capability) &&
    capability.accepted.includes(AUTHORED_PRIVATE_TOKEN)
  );
}

/** Map the form choice to what uploadSource() accepts. Authored content
 * yields a VerifiedAuthoredAttestation (sent as `user_authored_private`) or
 * throws `authored_unavailable`; there is no fallback to a legacy or public
 * class and no inferred publication consent. */
export function attestationToken(
  choice: AttestationChoice,
  capability: UploadAttestationCapability | null,
): AcquisitionAttestation {
  if (choice === "personal") return "personal_reading";
  if (!authoredUploadSupported(capability)) throw new SourceUploadError("authored_unavailable");
  const attestation = Object.freeze({}) as VerifiedAuthoredAttestation;
  issuedAuthoredAttestations.add(attestation);
  return attestation;
}

function parseCapability(raw: unknown): UploadAttestationCapability | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  // Own properties only: a field inherited through a polluted prototype must
  // never make an empty answer look capable (review F-01).
  const own = (key: string): unknown => (Object.hasOwn(o, key) ? o[key] : undefined);
  const accepted = own("accepted");
  if (!Array.isArray(accepted) || !accepted.every((t) => typeof t === "string")) return null;
  const rawAliases = own("aliases");
  const aliases: Record<string, string> = {};
  if (rawAliases && typeof rawAliases === "object") {
    for (const [k, v] of Object.entries(rawAliases as Record<string, unknown>)) {
      if (typeof v === "string") aliases[k] = v;
    }
  }
  const authoredDefault = own("authored_default");
  const capability = Object.freeze({
    accepted: Object.freeze([...(accepted as string[])]),
    authored_default: typeof authoredDefault === "string" ? authoredDefault : null,
    aliases: Object.freeze(aliases),
  }) as unknown as UploadAttestationCapability;
  verifiedCapabilities.add(capability);
  return capability;
}

let attestationsPromise: Promise<UploadAttestationCapability | null> | null = null;

/** Fetch the upload capability once per session. Resolves null on a 404 (an
 * API without the route), any error, or a malformed answer; a null result is
 * not cached, so a Retry refetches. A successful answer is reused. */
export function loadUploadAttestations(
  options: { refresh?: boolean } = {},
): Promise<UploadAttestationCapability | null> {
  if (attestationsPromise && !options.refresh) return attestationsPromise;
  const pending = (async () => {
    try {
      const response = await apiFetch(`${API_BASE}/sources/upload/attestations`);
      if (!response.ok) return null;
      return parseCapability(await response.json());
    } catch {
      return null;
    }
  })();
  attestationsPromise = pending;
  void pending.then((capability) => {
    if (capability === null && attestationsPromise === pending) attestationsPromise = null;
  });
  return pending;
}

/** Test seam: forget the cached capability. */
export function resetUploadAttestationsCache(): void {
  attestationsPromise = null;
}

/** The file name without its last extension ("notes.v2.md" -> "notes.v2").
 * Falls back to the whole name when stripping would leave nothing. */
export function fileStem(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

/** Upload a file without reflecting its name, content, or server detail into errors.
 *
 * `title` goes out as the multipart `title` field, which
 * interfaces/research/api/upload_routes.py accepts (`Form(None)`) and stores on
 * the document for every upload kind. A blank title is omitted so the backend
 * can derive it from the final document heading or filename. */
export async function uploadSource(
  file: File,
  acquisitionAttestation: AcquisitionAttestation,
  signal?: AbortSignal,
  title?: string,
): Promise<SourceUploadResponse> {
  // Runtime guard behind the type: nothing but "personal_reading" or an
  // issued authored attestation leaves here, and it is checked before any request.
  const wireToken = wireAttestation(acquisitionAttestation);
  const validationError = validateSourceUpload(file);
  if (validationError) throw new SourceUploadError(validationError);

  const form = new FormData();
  form.append("file", file);
  form.append("acquisition_attestation", wireToken);
  const explicitTitle = title?.trim();
  if (explicitTitle) form.append("title", explicitTitle);

  try {
    const response = await apiFetch(`${API_BASE}/sources/upload`, {
      method: "POST",
      body: form,
      signal,
    });
    if (!response.ok) {
      // Two different 409s: the EPUB ceremony, and a re-upload whose
      // attestation would widen the stored rights class. Only the fixed
      // detail.code is read — never server text.
      if (response.status === 409) {
        const body = (await response.json().catch(() => null)) as
          | { detail?: { code?: unknown } }
          | null;
        if (body?.detail?.code === "upload_attestation_conflict") {
          throw new SourceUploadError("attestation_conflict");
        }
      }
      throw new SourceUploadError(codeForStatus(response.status));
    }
    return (await response.json()) as SourceUploadResponse;
  } catch (error) {
    if (error instanceof SourceUploadError) throw error;
    if (signal?.aborted) throw new SourceUploadError("cancelled");
    throw new SourceUploadError("unavailable");
  }
}
