// Auth context + helpers for the Antiek-issued magic-link session.
//
// Backend contract:
//   POST /auth/request   { email }              → 200 { sent: true }
//   GET  /auth/callback?token=...&next=/        → 302 (Set-Cookie ANTIEK_SESSION)
//   POST /auth/logout                           → 204 (clears cookie)
//   GET  /auth/me                               → 200 { user_id, email, auth_method }
//                                                 401 if no valid session
//
// Cookies are cross-origin (antiek.ai → api.antiek.ai) so every
// request goes through apiFetch which sets credentials: "include".

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { API_BASE, apiFetch } from "./api";
import {
  authDiagnosticLayer,
  type AuthDiagnosticCode,
  type AuthDiagnosticLayer,
} from "./authDiagnosticCodes";

/** Layer A transport — never surface raw browser "Failed to fetch" to users. */
export const AUTH_TRANSPORT_FETCH_MESSAGE = "Cannot reach Antiek API";

// Every helper prepends API_BASE so the fetch goes to api.antiek.ai
// (the FastAPI), not antiek.ai (the Pages bundle). In dev, API_BASE
// is empty and Vite's /auth proxy handles the same-origin path.
function authUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export interface AuthIdentity {
  user_id: string;
  email: string | null;
  auth_method: string;
}

export type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; identity: AuthIdentity }
  | { status: "unauthenticated" };

export interface AuthContextValue {
  state: AuthState;
  /** Re-check /auth/me. Used after sign-in callback redirects back. */
  refresh: () => Promise<void>;
  /** POST /auth/logout, drop cookie, set state to unauthenticated. */
  signOut: () => Promise<void>;
}

const AuthCtx = createContext<AuthContextValue | null>(null);

async function fetchIdentity(): Promise<AuthIdentity | null> {
  const r = await apiFetch(authUrl("/auth/me"));
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(`auth/me HTTP ${r.status}`);
  const body = (await r.json()) as AuthIdentity;
  // The middleware returns "unauthenticated_local" when no auth env
  // vars are set (local dev). Treat that as authenticated so dev
  // doesn't loop through the login page.
  return body;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const identity = await fetchIdentity();
      if (identity) {
        setState({ status: "authenticated", identity });
      } else {
        setState({ status: "unauthenticated" });
      }
    } catch {
      // Network error → treat as unauthenticated; the login page can
      // show a generic "something went wrong" if needed.
      setState({ status: "unauthenticated" });
    }
  }, []);

  const signOut = useCallback(async () => {
    await apiFetch(authUrl("/auth/logout"), { method: "POST" });
    setState({ status: "unauthenticated" });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({ state, refresh, signOut }),
    [state, refresh, signOut],
  );
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}

export type AuthRequestResult =
  | { kind: "sent"; diagnostic_code: null; layer: null }
  | {
      kind: "error";
      code: string;
      message: string;
      diagnostic_code: AuthDiagnosticCode | null;
      layer: AuthDiagnosticLayer | null;
    };

function authRequestError(
  code: string,
  message: string,
  diagnostic_code: AuthDiagnosticCode | null = null,
): AuthRequestResult {
  return {
    kind: "error",
    code,
    message,
    diagnostic_code,
    layer: diagnostic_code ? authDiagnosticLayer(diagnostic_code) : null,
  };
}

export async function requestMagicLink(email: string, nextPath: string = "/"): Promise<AuthRequestResult> {
  try {
    const r = await apiFetch(authUrl("/auth/request"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, next: nextPath }),
    });
    if (r.ok) {
      return { kind: "sent", diagnostic_code: null, layer: null };
    }
    let detail: { code?: string; message?: string } = {};
    try {
      const body = (await r.json()) as { error?: { code?: string; message?: string }; detail?: { message?: string; code?: string } };
      detail = body.error ?? body.detail ?? {};
    } catch {
      // fall through to generic
    }
    if (r.status === 503) {
      return authRequestError(
        detail.code ?? "email_delivery_failed",
        detail.message ?? "Couldn't send the sign-in link.",
        "B-POLICY-EMAIL-503",
      );
    }
    return authRequestError(
      detail.code ?? `http_${r.status}`,
      detail.message ?? "Couldn't send the sign-in link.",
    );
  } catch {
    return authRequestError("transport_fetch_failed", AUTH_TRANSPORT_FETCH_MESSAGE, "A-TRANSPORT-FETCH");
  }
}

/** Login surface copy keyed by matrix failure_id (SPR-02). */
export function authLoginErrorDisplay(
  result: Extract<AuthRequestResult, { kind: "error" }>,
): { message: string; hint: string | null } {
  switch (result.diagnostic_code) {
    case "A-TRANSPORT-FETCH":
      return {
        message: AUTH_TRANSPORT_FETCH_MESSAGE,
        hint:
          "Check your connection, VPN, or browser extensions. If curl to the API works from your machine, the browser path may be blocked.",
      };
    case "B-POLICY-EMAIL-503":
      return {
        message: result.message,
        hint:
          "Sign-in email delivery failed. Ask your operator to verify Resend or AgentMail configuration on the server.",
      };
    default:
      return { message: result.message, hint: null };
  }
}
