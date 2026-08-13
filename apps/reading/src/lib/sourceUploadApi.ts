import { API_BASE, apiFetch } from "./api";

export const SOURCE_UPLOAD_MAX_BYTES = 64 * 1024 * 1024;
export const SOURCE_UPLOAD_MAX_LABEL = "64 MiB";

export const SOURCE_UPLOAD_EXTENSIONS = [
  ".pdf", ".html", ".htm", ".md", ".markdown", ".txt", ".text",
  ".doc", ".docx", ".docm", ".ppt", ".pps", ".pot", ".pptx",
  ".pptm", ".ppsx", ".ppsm", ".xlsx", ".xls", ".xlsm", ".xlsb",
  ".odt", ".ods", ".odp", ".rtf", ".csv",
] as const;

export type AcquisitionAttestation = "user_owned" | "personal_reading";

export interface SourceUploadResponse {
  document_id: string;
  detected_kind: string;
  reader_html_available: boolean;
  chunk_count: number;
}

export type SourceUploadErrorCode =
  | "too_large"
  | "unsupported"
  | "book_ceremony"
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

/** Upload a file without reflecting its name, content, or server detail into errors. */
export async function uploadSource(
  file: File,
  acquisitionAttestation: AcquisitionAttestation,
  signal?: AbortSignal,
): Promise<SourceUploadResponse> {
  const validationError = validateSourceUpload(file);
  if (validationError) throw new SourceUploadError(validationError);

  const form = new FormData();
  form.append("file", file);
  form.append("acquisition_attestation", acquisitionAttestation);

  try {
    const response = await apiFetch(`${API_BASE}/sources/upload`, {
      method: "POST",
      body: form,
      signal,
    });
    if (!response.ok) throw new SourceUploadError(codeForStatus(response.status));
    return (await response.json()) as SourceUploadResponse;
  } catch (error) {
    if (error instanceof SourceUploadError) throw error;
    if (signal?.aborted) throw new SourceUploadError("cancelled");
    throw new SourceUploadError("unavailable");
  }
}
