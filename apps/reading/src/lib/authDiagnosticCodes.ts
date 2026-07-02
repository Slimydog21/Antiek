/**
 * Closed union of auth diagnostic failure IDs — must match
 * docs/diagnostics/auth-failure-mode-matrix.md (version 2026-06-02).
 * Matrix commit: 59ee895ec78c69ab06ccdbbdd5927fcdff866432.
 *
 * Matrix is the source of truth. SPR-02+ import these codes for Login
 * errors, probes, and Playwright test names. Do not add codes here
 * without updating the matrix in the same commit.
 *
 * @see docs/diagnostics/auth-failure-mode-matrix.md
 */

/** Layer A = transport; B = policy; OPS = deployment/edge. */
export type AuthDiagnosticLayer = "A" | "B" | "OPS";

/** Immutable failure_id values from the SPR-01 matrix. */
export type AuthDiagnosticCode =
  | "A-TRANSPORT-FETCH"
  | "A-TRANSPORT-LOCAL-BACKEND"
  | "A-TRANSPORT-CORS"
  | "B-POLICY-ALLOWLIST-SILENT"
  | "B-POLICY-EMAIL-503"
  | "B-POLICY-CALLBACK-EXPIRED"
  | "B-POLICY-CALLBACK-INVALID"
  | "B-POLICY-CALLBACK-NOT-AUTH"
  | "OPS-INGEST-502"
  | "OPS-CF-403"
  | "OPS-COOKIE-DOMAIN"
  | "OPS-REDIRECT-API-HOST"
  | "OPS-MIDDLEWARE-COMMA";

export interface AuthDiagnosticDescriptor {
  code: AuthDiagnosticCode;
  layer: AuthDiagnosticLayer;
}

/** Maps every code to its matrix layer for grouping (e.g. Sentry, UI). */
export const AUTH_DIAGNOSTIC_LAYER_BY_CODE: Record<AuthDiagnosticCode, AuthDiagnosticLayer> = {
  "A-TRANSPORT-FETCH": "A",
  "A-TRANSPORT-LOCAL-BACKEND": "A",
  "A-TRANSPORT-CORS": "A",
  "B-POLICY-ALLOWLIST-SILENT": "B",
  "B-POLICY-EMAIL-503": "B",
  "B-POLICY-CALLBACK-EXPIRED": "B",
  "B-POLICY-CALLBACK-INVALID": "B",
  "B-POLICY-CALLBACK-NOT-AUTH": "B",
  "OPS-INGEST-502": "OPS",
  "OPS-CF-403": "OPS",
  "OPS-COOKIE-DOMAIN": "OPS",
  "OPS-REDIRECT-API-HOST": "OPS",
  "OPS-MIDDLEWARE-COMMA": "OPS",
};

export const AUTH_DIAGNOSTIC_CODES = Object.keys(
  AUTH_DIAGNOSTIC_LAYER_BY_CODE,
) as AuthDiagnosticCode[];

export function authDiagnosticLayer(code: AuthDiagnosticCode): AuthDiagnosticLayer {
  return AUTH_DIAGNOSTIC_LAYER_BY_CODE[code];
}

export function isAuthDiagnosticCode(value: string): value is AuthDiagnosticCode {
  return value in AUTH_DIAGNOSTIC_LAYER_BY_CODE;
}
