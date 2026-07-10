import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import wernerDefault from "../../brand/werner/poses/anchor/werner_default_v5_nano_corrected.png";
import { LemonButton, LemonInput } from "../../components/lemon";
import {
  authCallbackErrorDisplay,
  authLoginErrorDisplay,
  beginPasskeyLogin,
  beginPasskeyRegistration,
  finishPasskeyLogin,
  finishPasskeyRegistration,
  getPasskeyStatus,
  requestMagicLink,
  useAuth,
} from "../../lib/auth";
import type { AuthDiagnosticCode } from "../../lib/authDiagnosticCodes";
import { track, trackException } from "../../lib/analytics";

import "./Login.css";

type EmailStatus = "idle" | "sending" | "sent" | "error";
type PasskeyState = "checking" | "ready" | "absent" | "working" | "error";

function isPasskeyCancellation(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "AbortError");
}

function deviceLabel(): string {
  const ua = navigator.userAgent;
  if (/iPad/i.test(ua)) return "This iPad";
  if (/iPhone/i.test(ua)) return "This iPhone";
  if (/Mac/i.test(ua)) return "This Mac";
  return "This device";
}

function PasskeyMark({ active = false }: { active?: boolean }) {
  return (
    <span className="passkey-mark" data-active={active || undefined} aria-hidden="true">
      <span className="passkey-mark__arc passkey-mark__arc--one" />
      <span className="passkey-mark__arc passkey-mark__arc--two" />
      <span className="passkey-mark__stem" />
    </span>
  );
}

export default function Login() {
  const [email, setEmail] = useState("");
  const [emailStatus, setEmailStatus] = useState<EmailStatus>("idle");
  const [passkeyState, setPasskeyState] = useState<PasskeyState>("checking");
  const [errorMsg, setErrorMsg] = useState("");
  const [errorHint, setErrorHint] = useState<string | null>(null);
  const [diagnosticCode, setDiagnosticCode] = useState<AuthDiagnosticCode | null>(null);

  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { state, refresh } = useAuth();
  const isSetup = searchParams.get("setup") === "passkey";
  const nextPath = useMemo(
    () =>
      searchParams.get("next") ??
      (location.state as { from?: string } | null)?.from ??
      "/",
    [location.state, searchParams],
  );

  useEffect(() => {
    if (state.status === "authenticated" && !isSetup) {
      navigate(nextPath, { replace: true });
    }
  }, [isSetup, navigate, nextPath, state.status]);

  useEffect(() => {
    if (isSetup) return;
    let live = true;
    void getPasskeyStatus()
      .then(({ available }) => {
        if (live) setPasskeyState(available ? "ready" : "absent");
      })
      .catch(() => {
        if (live) setPasskeyState("absent");
      });
    return () => {
      live = false;
    };
  }, [isSetup]);

  useEffect(() => {
    const callbackError = searchParams.get("error");
    const display = authCallbackErrorDisplay(callbackError);
    if (!display) return;
    setEmailStatus("error");
    setErrorMsg(display.message);
    setErrorHint(display.hint);
    setDiagnosticCode(
      callbackError === "magic_link_expired"
        ? "B-POLICY-CALLBACK-EXPIRED"
        : callbackError === "magic_link_invalid"
          ? "B-POLICY-CALLBACK-INVALID"
          : callbackError === "not_authorized"
            ? "B-POLICY-CALLBACK-NOT-AUTH"
            : null,
    );
    const next = new URLSearchParams(searchParams);
    next.delete("error");
    navigate({ pathname: "/login", search: next.toString() ? `?${next}` : "" }, { replace: true });
  }, [navigate, searchParams]);

  async function unlockWithPasskey() {
    if (passkeyState === "working") return;
    setPasskeyState("working");
    setErrorMsg("");
    setErrorHint(null);
    track("passkey_login_started");
    try {
      const { ceremony_id, ...optionsJSON } = await beginPasskeyLogin();
      const credential = await startAuthentication({ optionsJSON });
      await finishPasskeyLogin(ceremony_id, credential);
      await refresh();
      track("passkey_login_succeeded");
      navigate(nextPath, { replace: true });
    } catch (error) {
      if (isPasskeyCancellation(error)) {
        setPasskeyState("ready");
        return;
      }
      const message = error instanceof Error ? error.message : "That passkey didn't unlock Antiek.";
      setErrorMsg(message);
      setErrorHint("Try again, use a nearby device, or recover with email.");
      setPasskeyState("error");
      trackException(error instanceof Error ? error : new Error(message));
    }
  }

  async function savePasskey() {
    if (passkeyState === "working") return;
    setPasskeyState("working");
    setErrorMsg("");
    try {
      const { ceremony_id, ...optionsJSON } = await beginPasskeyRegistration();
      const credential = await startRegistration({ optionsJSON });
      await finishPasskeyRegistration(ceremony_id, credential, deviceLabel());
      track("passkey_registered");
      setPasskeyState("ready");
      navigate(nextPath, { replace: true });
    } catch (error) {
      if (isPasskeyCancellation(error)) {
        setPasskeyState("absent");
        return;
      }
      const message = error instanceof Error ? error.message : "Antiek couldn't save that passkey.";
      setErrorMsg(message);
      setErrorHint("Your email sign-in is still active. You can try again safely.");
      setPasskeyState("error");
      trackException(error instanceof Error ? error : new Error(message));
    }
  }

  async function onEmailSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!email) return;
    setEmailStatus("sending");
    setErrorMsg("");
    setErrorHint(null);
    setDiagnosticCode(null);
    track("login_requested");
    const result = await requestMagicLink(email, nextPath);
    if (result.kind === "sent") {
      setEmailStatus("sent");
      track("login_link_sent");
      return;
    }
    const display = authLoginErrorDisplay(result);
    setEmailStatus("error");
    setErrorMsg(display.message);
    setErrorHint(display.hint);
    setDiagnosticCode(result.diagnostic_code);
    trackException(new Error(`Magic link failed: ${display.message}`));
  }

  const showPasskeyFirst = passkeyState !== "absent" && passkeyState !== "checking";
  const setupReady = isSetup && state.status === "authenticated";

  return (
    <main className="antiek-login" data-passkey-state={passkeyState}>
      <div className="antiek-login__grain" aria-hidden="true" />
      <section className="antiek-login__desk" aria-label="Antiek sign in">
        <header className="antiek-login__brand">
          <span className="antiek-login__wordmark">Antiek</span>
          <span className="antiek-login__edition">Private research workstation</span>
        </header>

        <div className="antiek-login__card">
          {setupReady ? (
            <>
              <div className="antiek-login__eyebrow"><span /> One last step</div>
              <h1>Leave email behind.</h1>
              <p className="antiek-login__lede">
                Save a passkey now. Next time, Antiek opens with Face ID, Touch ID, or your device PIN.
              </p>
              <button
                type="button"
                className="antiek-login__primary"
                onClick={() => void savePasskey()}
                disabled={passkeyState === "working"}
              >
                <PasskeyMark active={passkeyState === "working"} />
                <span>
                  <strong>{passkeyState === "working" ? "Saving passkey…" : `Save to ${deviceLabel()}`}</strong>
                  <small>Encrypted and synced by your device</small>
                </span>
                <span className="antiek-login__arrow" aria-hidden="true">→</span>
              </button>
              {errorMsg && (
                <div className="antiek-login__error" role="alert">
                  <strong>{errorMsg}</strong>
                  {errorHint && <span>{errorHint}</span>}
                </div>
              )}
              <button className="antiek-login__quiet" type="button" onClick={() => navigate(nextPath, { replace: true })}>
                Do this later
              </button>
            </>
          ) : showPasskeyFirst ? (
            <>
              <div className="antiek-login__eyebrow"><span /> Welcome back</div>
              <h1>Pick up the thread.</h1>
              <p className="antiek-login__lede">Your workstation is exactly where you left it.</p>
              <button
                type="button"
                className="antiek-login__primary"
                onClick={() => void unlockWithPasskey()}
                disabled={passkeyState === "working"}
              >
                <PasskeyMark active={passkeyState === "working"} />
                <span>
                  <strong>{passkeyState === "working" ? "Unlocking…" : "Unlock with passkey"}</strong>
                  <small>Face ID, Touch ID, or a nearby device</small>
                </span>
                <span className="antiek-login__arrow" aria-hidden="true">→</span>
              </button>

              {(passkeyState === "error" || errorMsg) && (
                <div className="antiek-login__error" role="alert">
                  <strong>{errorMsg}</strong>
                  {errorHint && <span>{errorHint}</span>}
                </div>
              )}

              <details className="antiek-login__recovery">
                <summary>Use email recovery</summary>
                <EmailForm
                  email={email}
                  setEmail={setEmail}
                  status={emailStatus}
                  onSubmit={onEmailSubmit}
                  errorMsg={emailStatus === "error" ? errorMsg : ""}
                  errorHint={emailStatus === "error" ? errorHint : null}
                  diagnosticCode={diagnosticCode}
                />
              </details>
            </>
          ) : emailStatus === "sent" ? (
            <div className="antiek-login__sent" role="status">
              <div className="antiek-login__sent-mark" aria-hidden="true">✓</div>
              <div className="antiek-login__eyebrow"><span /> Link sent</div>
              <h1>Check your phone.</h1>
              <p className="antiek-login__lede">
                Open the message sent to <strong>{email}</strong>. Antiek will help you save a passkey so this is the last email detour.
              </p>
              <button type="button" className="antiek-login__quiet" onClick={() => setEmailStatus("idle")}>
                Use a different email
              </button>
            </div>
          ) : (
            <>
              <div className="antiek-login__eyebrow"><span /> First unlock</div>
              <h1>Enter your workstation.</h1>
              <p className="antiek-login__lede">
                Verify your email once. Then replace it with a passkey on your phone, iPad, or computer.
              </p>
              <EmailForm
                email={email}
                setEmail={setEmail}
                status={emailStatus}
                onSubmit={onEmailSubmit}
                errorMsg={errorMsg}
                errorHint={errorHint}
                diagnosticCode={diagnosticCode}
              />
            </>
          )}
        </div>

        <footer className="antiek-login__footer">
          <span>Private by default</span>
          <span aria-hidden="true">·</span>
          <a href="/trust">How Antiek protects your work</a>
        </footer>
      </section>

      <aside className="antiek-login__world" aria-label="Werner keeps watch over your research">
        <div className="ice-portal" aria-hidden="true">
          <span className="ice-portal__ring ice-portal__ring--1" />
          <span className="ice-portal__ring ice-portal__ring--2" />
          <span className="ice-portal__ring ice-portal__ring--3" />
          <span className="ice-portal__core"><PasskeyMark active={passkeyState === "working"} /></span>
        </div>
        <div className="antiek-login__werner-wrap">
          <span className="antiek-login__watch-note">Werner kept your place.</span>
          <img src={wernerDefault} alt="Werner, Antiek's penguin" className="antiek-login__werner" />
        </div>
        <blockquote>
          <span>“</span>
          The good question is still waiting.
        </blockquote>
        <div className="antiek-login__coordinates" aria-hidden="true">78° S · PRIVATE CHANNEL · SIGNAL CLEAR</div>
      </aside>
    </main>
  );
}

interface EmailFormProps {
  email: string;
  setEmail: (value: string) => void;
  status: EmailStatus;
  onSubmit: (event: React.FormEvent) => void;
  errorMsg: string;
  errorHint: string | null;
  diagnosticCode: AuthDiagnosticCode | null;
}

function EmailForm({ email, setEmail, status, onSubmit, errorMsg, errorHint, diagnosticCode }: EmailFormProps) {
  return (
    <form onSubmit={onSubmit} className="antiek-login__form">
      <label>
        <span>Email</span>
        <LemonInput
          type="email"
          autoFocus
          autoComplete="email"
          required
          disabled={status === "sending"}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          sizing="lg"
          wrapperClassName="w-full"
        />
      </label>
      <LemonButton type="submit" variant="primary" size="lg" fullWidth disabled={status === "sending" || !email}>
        {status === "sending" ? "Sending secure link…" : "Continue with email"}
      </LemonButton>
      {status === "error" && errorMsg && (
        <div className="antiek-login__error" role="alert" data-auth-diagnostic={diagnosticCode ?? undefined}>
          <strong>{errorMsg}</strong>
          {errorHint && <span>{errorHint}</span>}
        </div>
      )}
    </form>
  );
}
