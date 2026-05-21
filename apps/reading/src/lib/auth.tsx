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

import { apiFetch } from "./api";

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
  const r = await apiFetch("/auth/me");
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
    await apiFetch("/auth/logout", { method: "POST" });
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
  | { kind: "sent" }
  | { kind: "error"; code: string; message: string };

export async function requestMagicLink(email: string, nextPath: string = "/"): Promise<AuthRequestResult> {
  try {
    const r = await apiFetch("/auth/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, next: nextPath }),
    });
    if (r.ok) {
      return { kind: "sent" };
    }
    let detail: { code?: string; message?: string } = {};
    try {
      const body = (await r.json()) as { error?: { code?: string; message?: string }; detail?: { message?: string; code?: string } };
      detail = body.error ?? body.detail ?? {};
    } catch {
      // fall through to generic
    }
    return {
      kind: "error",
      code: detail.code ?? `http_${r.status}`,
      message: detail.message ?? "Couldn't send the sign-in link.",
    };
  } catch (err) {
    return {
      kind: "error",
      code: "network_error",
      message: err instanceof Error ? err.message : "Network error.",
    };
  }
}
