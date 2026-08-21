import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface ProjectionStyle {
  name: string;
  label: string;
  description: string;
  builtin: boolean;
  source_fidelity: boolean;
  theme_css: string;
}

export interface StyleDraft {
  name: string;
  label: string;
  description: string;
  source_fidelity: boolean;
  theme_css: string;
}

export interface ArtifactStatus {
  artifact_id: string;
  investigation_id: string;
  selected_style: string | null;
  latest_version: number;
}

export interface RenderedArtifact {
  html: Blob;
  artifactId: string;
  style: string;
  version: string;
  hash: string;
  sourceHash: string;
}

const SHA256 = /^[a-f0-9]{64}$/;
const POSITIVE_VERSION = /^[1-9][0-9]*$/;

function receiptHeaders(
  response: Response,
  expectedArtifactId: string,
  expectedStyle: string | undefined,
  apply: boolean,
): Omit<RenderedArtifact, "html"> {
  const artifactId = response.headers.get("X-Artifact-ID");
  const style = response.headers.get("X-Artifact-Style");
  const version = response.headers.get("X-Artifact-Version");
  const hash = response.headers.get("X-Content-SHA256");
  const sourceHash = response.headers.get("X-Source-SHA256");
  const valid =
    artifactId === expectedArtifactId &&
    typeof style === "string" && style.length > 0 &&
    (expectedStyle === undefined || style === expectedStyle) &&
    typeof version === "string" && (apply ? POSITIVE_VERSION.test(version) : version === "preview") &&
    typeof hash === "string" && SHA256.test(hash) &&
    typeof sourceHash === "string" && SHA256.test(sourceHash);
  if (!valid) {
    throw new ApiError(
      "The render response carried an invalid or mismatched artifact receipt; it was refused.",
      502,
      "invalid artifact receipt",
    );
  }
  return { artifactId, style, version, hash, sourceHash };
}

async function checked(response: Response, action: string): Promise<Response> {
  if (!response.ok) {
    let message = `${action} failed (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Keep the bounded status message when the response is not JSON.
    }
    throw new ApiError(message, response.status, message);
  }
  return response;
}

export async function listStyles(signal?: AbortSignal): Promise<ProjectionStyle[]> {
  const response = await checked(
    await apiFetch(`${API_BASE}/styles`, { signal }),
    "Loading styles",
  );
  return ((await response.json()) as { styles: ProjectionStyle[] }).styles;
}

export async function getArtifactStatus(
  investigationId: string,
  signal?: AbortSignal,
): Promise<ArtifactStatus | null> {
  const response = await apiFetch(
    `${API_BASE}/research/${encodeURIComponent(investigationId)}/artifact`,
    { signal },
  );
  if (response.status === 404) return null;
  await checked(response, "Loading artifact status");
  return response.json();
}

export async function saveStyle(draft: StyleDraft): Promise<ProjectionStyle> {
  const response = await checked(
    await apiFetch(`${API_BASE}/styles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    }),
    "Saving style",
  );
  return response.json();
}

/** Remove a user fork. Builtins return 409; unknown names return 404. */
export async function deleteStyle(name: string, signal?: AbortSignal): Promise<void> {
  await checked(
    await apiFetch(`${API_BASE}/styles/${encodeURIComponent(name)}`, {
      method: "DELETE",
      signal,
    }),
    "Deleting style",
  );
}

export async function renderArtifact(
  artifactId: string,
  style: string | undefined,
  apply: boolean,
  signal?: AbortSignal,
): Promise<RenderedArtifact> {
  const query = style === undefined ? "" : `?style=${encodeURIComponent(style)}`;
  const route = `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/render${query}`;
  const response = await checked(
    await apiFetch(route, { method: apply ? "POST" : "GET", signal }),
    apply ? "Applying style" : "Building preview",
  );
  const receipt = receiptHeaders(response, artifactId, style, apply);
  return { html: await response.blob(), ...receipt };
}

export function artifactVersionUrl(artifactId: string, version?: string): string {
  const suffix = version ? encodeURIComponent(version) : "latest";
  return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/versions/${suffix}`;
}
