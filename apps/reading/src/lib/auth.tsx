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
import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
  RegistrationResponseJSON,
} from "@simplewebauthn/browser";

import { API_BASE, apiFetch } from "./api";
import {
  authDiagnosticLayer,
  type AuthDiagnosticCode,
  type AuthDiagnosticLayer,
} from "./authDiagnosticCodes";
import { posthog, posthogEnabled } from "./posthogClient";

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

  // Link the PostHog person to the substrate session as auth state resolves.
  // distinct_id is the substrate user_id (never PII); email + auth_method are
  // set as person properties on purpose (person-level analysis on a
  // GDPR-resident, identified_only project), with first-touch auth method as
  // $set_once. reset() on sign-out. No-op without a token. Lives here rather
  // than a component mounted in App.tsx so the route tree stays untouched.
  useEffect(() => {
    if (!posthogEnabled || state.status === "loading") return;
    if (state.status === "authenticated") {
      const { user_id, email, auth_method } = state.identity;
      posthog.identify(
        user_id,
        { email: email ?? undefined, auth_method },
        { first_seen_auth_method: auth_method },
      );
      return;
    }
    posthog.reset();
  }, [state]);

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
  | { kind: "sent"; attempt_id: string; claim_secret: string; device_code: string; diagnostic_code: null; layer: null }
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
      const body = (await r.json()) as { attempt_id: string; claim_secret: string; device_code: string };
      return {
        kind: "sent",
        attempt_id: body.attempt_id,
        claim_secret: body.claim_secret,
        device_code: body.device_code,
        diagnostic_code: null,
        layer: null,
      };
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

export type LoginClaimResult =
  | { status: "pending" }
  | { status: "authenticated"; setup_passkey: boolean; next: string }
  | { status: "expired" };

export async function claimLogin(attemptId: string, claimSecret: string): Promise<LoginClaimResult> {
  const r = await apiFetch(authUrl("/auth/claim"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt_id: attemptId, claim_secret: claimSecret }),
  });
  if (r.status === 202) return { status: "pending" };
  if (r.status === 410) return { status: "expired" };
  if (!r.ok) throw new Error("Antiek couldn't finish the device handoff.");
  const body = (await r.json()) as { setup_passkey: boolean; next: string };
  return { status: "authenticated", ...body };
}

export async function approveLogin(attemptId: string): Promise<void> {
  const r = await apiFetch(authUrl("/auth/approve"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt_id: attemptId }),
  });
  if (!r.ok) throw new Error("This device handoff has expired.");
}

export interface PasskeyStatus {
  available: boolean;
  count: number | null;
}

export interface PasskeyOptions extends PublicKeyCredentialRequestOptionsJSON {
  ceremony_id: string;
}

export interface PasskeyRegistrationOptions extends PublicKeyCredentialCreationOptionsJSON {
  ceremony_id: string;
}

async function authJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(authUrl(path), init);
  if (!r.ok) {
    let message = "Antiek couldn't complete that request.";
    try {
      const body = (await r.json()) as { detail?: { message?: string } };
      message = body.detail?.message ?? message;
    } catch {
      // Keep the closed user-safe fallback.
    }
    throw new Error(message);
  }
  return (await r.json()) as T;
}

export async function getPasskeyStatus(): Promise<PasskeyStatus> {
  return authJSON<PasskeyStatus>("/auth/passkey/status");
}

export async function beginPasskeyLogin(): Promise<PasskeyOptions> {
  return authJSON<PasskeyOptions>("/auth/passkey/login/options", { method: "POST" });
}

export async function finishPasskeyLogin(
  ceremonyId: string,
  credential: AuthenticationResponseJSON,
): Promise<void> {
  const r = await apiFetch(authUrl("/auth/passkey/login/verify"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ceremony_id: ceremonyId, credential }),
  });
  if (!r.ok) {
    let message = "That passkey didn't unlock Antiek.";
    try {
      const body = (await r.json()) as { detail?: { message?: string } };
      message = body.detail?.message ?? message;
    } catch {
      // Keep the closed user-safe fallback.
    }
    throw new Error(message);
  }
}

export async function beginPasskeyRegistration(): Promise<PasskeyRegistrationOptions> {
  return authJSON<PasskeyRegistrationOptions>("/auth/passkey/register/options", { method: "POST" });
}

export async function finishPasskeyRegistration(
  ceremonyId: string,
  credential: RegistrationResponseJSON,
  label: string,
): Promise<void> {
  await authJSON<{ registered: true }>("/auth/passkey/register/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ceremony_id: ceremonyId, credential, label }),
  });
}

export interface SavedPasskey {
  id: string;
  label: string;
  backed_up: boolean;
  created_at: number;
  last_used_at: number | null;
}

export async function listPasskeys(): Promise<SavedPasskey[]> {
  const response = await authJSON<{ passkeys: SavedPasskey[] }>("/auth/passkeys");
  return response.passkeys;
}

export async function removePasskey(id: string): Promise<void> {
  const r = await apiFetch(authUrl(`/auth/passkeys/${encodeURIComponent(id)}`), { method: "DELETE" });
  if (!r.ok) throw new Error("Antiek couldn't remove that passkey.");
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

/** Closed set for ``/login?error=`` from callback redirects (SPR-03). */
export type AuthCallbackErrorCode =
  | "magic_link_expired"
  | "magic_link_invalid"
  | "not_authorized";

const CALLBACK_ERROR_COPY: Record<
  AuthCallbackErrorCode,
  { message: string; hint: string }
> = {
  magic_link_expired: {
    message: "This sign-in link expired.",
    hint: "Request a new link from the form below. Links expire in 15 minutes.",
  },
  magic_link_invalid: {
    message: "This sign-in link is not valid.",
    hint: "The link may be incomplete or already used. Request a new one below.",
  },
  not_authorized: {
    message: "This email is not authorized for Antiek.",
    hint: "Ask your operator to add your address to the server allowlist.",
  },
};

export function authCallbackErrorDisplay(
  code: string | null,
): { message: string; hint: string } | null {
  if (!code) return null;
  if (code === "magic_link_expired" || code === "magic_link_invalid" || code === "not_authorized") {
    return CALLBACK_ERROR_COPY[code];
  }
  return null;
}
