import { setTabOwner, suspendTabDispatch } from "../workspace/tabTreeOwner";
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

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
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
import { setReadingStateOwner } from "../hooks/useReadingState";
import { setSectionProseOwner, suspendSectionProseDispatch } from "../modes/Write/sectionProseOwner";

/** Layer A transport — never surface raw browser "Failed to fetch" to users. */
export const AUTH_TRANSPORT_FETCH_MESSAGE = "Cannot reach Antiek API";

/** F-03: the full-viewport message while /auth/me cannot answer. */
export const AUTH_UNAVAILABLE_COPY = "Antiek can't reach its server right now.";

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

/** Why /auth/me could not answer (F-03). None of these is an identity. */
export type AuthUnavailableReason = "offline" | "server" | "malformed";

export type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; identity: AuthIdentity }
  /**
   * `inferred`: no readable /auth/me answer, but /health proved the API is
   * up, so this is taken to be a CORS-masked 401 (P-02). It routes exactly
   * like a real 401; it only differs in what it may erase (neither the
   * reading-state owner nor the analytics identity).
   */
  | { status: "unauthenticated"; inferred?: true }
  /**
   * /auth/me could not give an identity answer: the fetch threw (offline),
   * the server answered with a transient failure (server), or a 200 body was
   * unreadable (malformed). AuthProvider renders its own full-viewport
   * screen INSTEAD of its children in this state, so no consumer (notably
   * RequireAuth in App.tsx) ever observes it.
   */
  | { status: "unavailable"; reason: AuthUnavailableReason };

export interface AuthContextValue {
  state: AuthState;
  /** Re-check /auth/me. Used after sign-in callback redirects back. */
  refresh: () => Promise<void>;
  /** POST /auth/logout, drop cookie, set state to unauthenticated. */
  signOut: () => Promise<void>;
}

const AuthCtx = createContext<AuthContextValue | null>(null);

type IdentityAnswer =
  | { kind: "identity"; identity: AuthIdentity }
  /**
   * `inferred`: /auth/me gave no readable answer, but /health proved the API
   * is up, so the failure is taken to be a CORS-masked 401 (P-02). Treated as
   * unauthenticated, but NOT as proof of identity: the reading-state owner is
   * left alone (only a real 401 or a sign-out clears it).
   */
  | { kind: "anonymous"; inferred?: boolean }
  | { kind: "unavailable"; reason: AuthUnavailableReason };

/** Upper bound on the /health reachability probe. */
export const HEALTH_PROBE_TIMEOUT_MS = 3_000;

/**
 * P-02 workaround: is the API reachable at all?
 *
 * In production the SPA (antiek.ai) calls the API (api.antiek.ai)
 * cross-origin, and the auth middleware emits its 401 on /auth/me OUTSIDE
 * CORSMiddleware, with no access-control-allow-origin. The browser therefore
 * rejects a logged-out visitor's /auth/me with a TypeError, exactly as it
 * would if the API were down. /health is public and does carry CORS headers
 * on its 200, so one probe tells the two apart: any answer below 500 means
 * the API is up (so the /auth/me failure was a masked 401); a network error,
 * a 5xx or no answer within HEALTH_PROBE_TIMEOUT_MS means it is not.
 *
 * REMOVE this probe once the backend emits CORS headers on its 401s (P-02,
 * Astra backend INBOX): /auth/me will then answer 401 readably and this
 * function becomes dead weight on every logged-out page load.
 */
async function apiIsReachable(): Promise<boolean> {
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = setTimeout(() => controller?.abort(), HEALTH_PROBE_TIMEOUT_MS);
  try {
    const probe = apiFetch(authUrl("/health"), { signal: controller?.signal });
    const r = await Promise.race([
      probe,
      new Promise<never>((_, reject) => {
        controller?.signal.addEventListener("abort", () => reject(new Error("health probe timed out")));
      }),
    ]);
    return r.status < 500;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** A transport failure or unreadable 200 on /auth/me: masked 401 or real outage? */
async function classifyUnreadable(reason: AuthUnavailableReason): Promise<IdentityAnswer> {
  return (await apiIsReachable())
    ? { kind: "anonymous", inferred: true }
    : { kind: "unavailable", reason };
}

/**
 * Statuses that mean "the server could not answer right now", as opposed to
 * an answer about who you are. 5xx covers a backend restart behind the
 * Cloudflare tunnel (502/503/504/530); 408 and 429 are retryable by
 * definition. A 401 is the one identity answer ("no session"). Other 4xx
 * (403, 404, …) keep their pre-F-03 meaning, unauthenticated: they are
 * definitive answers that a Retry will not change, and Storybook's /auth/me
 * probe is a static-server 404 that the Topbar/AppShell stories (and their
 * lost-pixel baselines) rely on settling to unauthenticated.
 */
function isTransientStatus(status: number): boolean {
  return status >= 500 || status === 408 || status === 429;
}

function isIdentity(body: unknown): body is AuthIdentity {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Record<string, unknown>;
  return typeof b.user_id === "string" && b.user_id !== "" && typeof b.auth_method === "string";
}

async function fetchIdentity(): Promise<IdentityAnswer> {
  let r: Response;
  try {
    r = await apiFetch(authUrl("/auth/me"));
  } catch {
    // fetch rejects with a TypeError when the network, DNS, TLS or CORS
    // fails. In prod that includes the logged-out 401 (P-02: no CORS
    // headers), so ask /health before calling it an outage.
    return classifyUnreadable("offline");
  }
  if (r.status === 401) return { kind: "anonymous" };
  if (!r.ok) {
    return isTransientStatus(r.status)
      ? { kind: "unavailable", reason: "server" }
      : { kind: "anonymous" };
  }
  let body: unknown;
  try {
    body = await r.json();
  } catch {
    // e.g. an HTML error page with a 200 from a proxy (SyntaxError).
    return classifyUnreadable("malformed");
  }
  // The middleware returns auth_method "unauthenticated_local" when no auth
  // env vars are set (local dev). That is a real identity (user_id
  // "__operator__"), so dev doesn't loop through the login page.
  if (!isIdentity(body)) return classifyUnreadable("malformed");
  return { kind: "identity", identity: body };
}

const UNAVAILABLE_HINT: Record<AuthUnavailableReason, string> = {
  offline: "Check your connection, then try again.",
  server: "The server didn't answer. It may be restarting.",
  malformed: "The server sent a reply Antiek couldn't read.",
};

/**
 * Full-viewport outage screen (F-03). Plain markup on purpose: it renders in
 * place of the whole app, from the entry chunk, so it must not import
 * components/lemon/* (the lemon chunk's budget headroom is ~7.5 KB).
 */
function AuthUnavailableScreen({
  reason,
  onRetry,
}: {
  reason: AuthUnavailableReason;
  onRetry: () => Promise<void>;
}) {
  const [retrying, setRetrying] = useState(false);
  const retry = useCallback(async () => {
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  }, [onRetry]);
  return (
    <main
      role="alert"
      data-auth-unavailable={reason}
      className="min-h-screen flex items-center justify-center p-8 bg-ice-2 dark:bg-space-2 text-ink dark:text-bright font-sans"
    >
      <div className="max-w-md text-center">
        <p className="text-lg font-semibold mb-2">{AUTH_UNAVAILABLE_COPY}</p>
        <p className="text-sm text-shadow-1 dark:text-moonlight mb-6">{UNAVAILABLE_HINT[reason]}</p>
        <button
          type="button"
          onClick={() => void retry()}
          disabled={retrying}
          aria-busy={retrying}
          className="rounded-md px-4 py-2 text-sm font-semibold bg-sun text-ink hover:bg-sun-hover disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink dark:focus-visible:ring-bright focus-visible:ring-offset-2"
        >
          Retry
        </button>
      </div>
    </main>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const refreshEpochRef = useRef(0);

  const refresh = useCallback(async () => {
    const epoch = ++refreshEpochRef.current;
    let answer: IdentityAnswer;
    try {
      answer = await fetchIdentity();
    } catch {
      // fetchIdentity classifies every failure itself; this is belt and
      // braces for a bug in that classification, and it errs to unavailable.
      answer = { kind: "unavailable", reason: "offline" };
    }
    if (refreshEpochRef.current !== epoch) return;
    if (answer.kind === "unavailable") {
      suspendSectionProseDispatch();
      suspendTabDispatch();
      // Unknown transport failure is not an identity transition. Keep the
      // reading-state owner until /auth/me proves a different or null user;
      // this preserves pending work across a transient API outage. F-03:
      // and do not claim "unauthenticated" either — that sent a signed-in
      // user to /login during every backend restart.
      setState({ status: "unavailable", reason: answer.reason });
      return;
    }
    const identity = answer.kind === "identity" ? answer.identity : null;
    // An inferred (CORS-masked) 401 is not proof of a null user: leave the
    // reading-state owner as it was, the pre-F-03 behaviour for transport
    // failures, so pending work survives a blip that /health happened to
    // outlive.
    if (!(answer.kind === "anonymous" && answer.inferred)) {
      setReadingStateOwner(identity?.user_id ?? null);
      setSectionProseOwner(identity?.user_id ?? null);
      setTabOwner(identity?.user_id ?? null);
    } else {
      suspendSectionProseDispatch();
      suspendTabDispatch();
    }
    if (identity) {
      setState({ status: "authenticated", identity });
    } else if (answer.kind === "anonymous" && answer.inferred) {
      setState({ status: "unauthenticated", inferred: true });
    } else {
      setState({ status: "unauthenticated" });
    }
  }, []);

  const signOut = useCallback(async () => {
    // A logout invalidates every identity answer already in flight; it must
    // never be reversed by an older /auth/me response.
    refreshEpochRef.current += 1;
    setReadingStateOwner(null);
    setSectionProseOwner(null);
    setTabOwner(null);
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
    // An outage (unavailable) is not a sign-out: never reset the analytics
    // identity for it. Nor for an INFERRED 401 (critic F-05): that answer is
    // outage-shaped (the browser saw a transport failure), so it keeps the
    // identity until a real 401 or a sign-out proves the user is gone.
    if (!posthogEnabled || state.status === "loading" || state.status === "unavailable") return;
    if (state.status === "unauthenticated" && state.inferred) return;
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
  return (
    <AuthCtx.Provider value={value}>
      {state.status === "unavailable" ? (
        <AuthUnavailableScreen reason={state.reason} onRetry={refresh} />
      ) : (
        children
      )}
    </AuthCtx.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}

export type AuthRequestResult =
  | { kind: "sent"; attempt_id: string; claim_secret: string; diagnostic_code: null; layer: null }
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
      const body = (await r.json()) as { attempt_id: string; claim_secret: string };
      // The 4-digit code is deliberately NOT in the API response — it
      // only ever exists inside the delivered email, so typing it into
      // the browser is real email-possession proof.
      return {
        kind: "sent",
        attempt_id: body.attempt_id,
        claim_secret: body.claim_secret,
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
  | { status: "invalid_code"; remaining_attempts: number }
  | { status: "rate_limited" }
  | { status: "expired" };

/**
 * Claim the sign-in session for an attempt.
 *
 * With `code` (the 4 digits from the email): the single-device unlock —
 * the server verifies the code and mints the session immediately.
 * Without it: the two-device path — 202 until the email-click device
 * approved via POST /auth/approve.
 */
export async function claimLogin(
  attemptId: string,
  claimSecret: string,
  code?: string,
): Promise<LoginClaimResult> {
  const r = await apiFetch(authUrl("/auth/claim"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      attempt_id: attemptId,
      claim_secret: claimSecret,
      ...(code !== undefined ? { code } : {}),
    }),
  });
  if (r.status === 202) return { status: "pending" };
  if (r.status === 410) return { status: "expired" };
  if (r.status === 429) return { status: "rate_limited" };
  if (r.status === 400) {
    try {
      const body = (await r.json()) as {
        detail?: { code?: string; remaining_attempts?: number };
      };
      if (body.detail?.code === "invalid_code") {
        return { status: "invalid_code", remaining_attempts: body.detail.remaining_attempts ?? 0 };
      }
    } catch {
      // fall through to the generic error
    }
    throw new Error("Antiek couldn't finish the device handoff.");
  }
  if (!r.ok) throw new Error("Antiek couldn't finish the device handoff.");
  const body = (await r.json()) as { setup_passkey: boolean; next: string };
  return { status: "authenticated", setup_passkey: body.setup_passkey, next: body.next };
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
