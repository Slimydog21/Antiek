import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { LemonButton, LemonInput } from "../../components/lemon";
import {
  authCallbackErrorDisplay,
  authLoginErrorDisplay,
  approveLogin,
  beginPasskeyLogin,
  beginPasskeyRegistration,
  finishPasskeyLogin,
  finishPasskeyRegistration,
  getPasskeyStatus,
  claimLogin,
  requestMagicLink,
  useAuth,
} from "../../lib/auth";
import type { AuthDiagnosticCode } from "../../lib/authDiagnosticCodes";
import { track, trackException } from "../../lib/analytics";
import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import { emitWernerExperience } from "../../werner/reactionBus";

import "./Login.css";

type EmailStatus = "idle" | "sending" | "sent" | "approved" | "expired" | "error";
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
  const [handoff, setHandoff] = useState<{ attemptId: string; claimSecret: string; deviceCode: string } | null>(null);
  const [approvalWorking, setApprovalWorking] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { state, refresh } = useAuth();
  const isSetup = searchParams.get("setup") === "passkey";
  const approvalAttempt = searchParams.get("approve");
  const approvalCode = searchParams.get("code");
  const nextPath = useMemo(
    () =>
      searchParams.get("next") ??
      (location.state as { from?: string } | null)?.from ??
      "/",
    [location.state, searchParams],
  );

  useEffect(() => {
    if (state.status === "authenticated" && !isSetup && !approvalAttempt) {
      navigate(nextPath, { replace: true });
    }
  }, [approvalAttempt, isSetup, navigate, nextPath, state.status]);

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

  useEffect(() => {
    if (!handoff || emailStatus !== "sent") return;
    let live = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const result = await claimLogin(handoff.attemptId, handoff.claimSecret);
        if (!live) return;
        if (result.status === "authenticated") {
          setEmailStatus("approved");
          await refresh();
          navigate(
            result.setup_passkey
              ? `/login?setup=passkey&next=${encodeURIComponent(result.next)}`
              : result.next,
            { replace: true },
          );
          return;
        }
        if (result.status === "expired") {
          setEmailStatus("expired");
          setErrorMsg("That handoff expired.");
          setErrorHint("Send a fresh one and leave this screen open.");
          return;
        }
      } catch {
        // A brief network interruption should not cancel a valid handoff.
      }
      if (live) timer = window.setTimeout(poll, 1800);
    };
    void poll();
    return () => {
      live = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [emailStatus, handoff, navigate, refresh]);

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
      // Living-TV: welcome beat as Antiek unlocks.
      emitWernerExperience("highlight");
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
      emitWernerExperience("fail");
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
      emitWernerExperience("highlight");
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
      setHandoff({ attemptId: result.attempt_id, claimSecret: result.claim_secret, deviceCode: result.device_code });
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

  async function approveHandoff() {
    if (!approvalAttempt || approvalWorking) return;
    setApprovalWorking(true);
    setErrorMsg("");
    try {
      await approveLogin(approvalAttempt);
      navigate("/login?approved=1", { replace: true });
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "This device handoff has expired.");
      setApprovalWorking(false);
    }
  }

  if (approvalAttempt) {
    return (
      <main className="antiek-login antiek-login--receipt">
        <section className="handoff-receipt">
          <div className="antiek-login__eyebrow"><span /> Device handoff</div>
          <h1>Does your other screen show this code?</h1>
          <p className="handoff-code" aria-label={`Device code ${approvalCode}`}>{approvalCode}</p>
          <p>Only approve when the computer or iPad where you started shows the same four digits.</p>
          <button type="button" className="antiek-login__primary" onClick={() => void approveHandoff()} disabled={approvalWorking}>
            <span aria-hidden="true">✓</span>
            <span><strong>{approvalWorking ? "Approving…" : "Yes, unlock that screen"}</strong><small>One-time approval · expires in 15 minutes</small></span>
            <span className="antiek-login__arrow" aria-hidden="true">→</span>
          </button>
          {errorMsg && <div className="antiek-login__error" role="alert"><strong>{errorMsg}</strong></div>}
        </section>
      </main>
    );
  }

  if (searchParams.get("approved") === "1") {
    return (
      <main className="antiek-login antiek-login--receipt">
        <section className="handoff-receipt" role="status">
          <span className="handoff-receipt__stamp">Approved</span>
          <div className="antiek-login__eyebrow"><span /> Device handoff</div>
          <h1>Your other screen is unlocking.</h1>
          <p>Return to the computer or iPad where you started. You can close this page.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="antiek-login" data-passkey-state={passkeyState}>
      <div className="antiek-login__grain" aria-hidden="true" />
      <section className="antiek-login__desk" aria-label="Antiek sign in">
        <header className="antiek-login__brand">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="login-werner-brand"
            className="antiek-login__werner"
            width={56}
            height={56}
          />
          <span className="antiek-login__wordmark">Antiek</span>
          <span className="antiek-login__edition">Private research workstation</span>
          <img
            src={livingTvArt}
            alt=""
            aria-hidden="true"
            data-testid="login-living-tv-art"
            className="antiek-login__living-tv antiek-living-tv-invent"
            style={{
              width: "100%",
              maxWidth: 280,
              height: 72,
              objectFit: "cover",
              objectPosition: "center top",
              borderRadius: 8,
              marginTop: 12,
              display: "block",
            }}
            loading="lazy"
            decoding="async"
          />
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
              <div className="antiek-login__eyebrow"><span /> Handoff waiting</div>
              <h1>Now check your phone.</h1>
              <p className="antiek-login__lede">
                Open the message sent to <strong>{email}</strong>. Approve it there; this screen will unlock itself.
              </p>
              <div className="handoff-code handoff-code--desk" aria-label={`Device code ${handoff?.deviceCode}`}>
                <small>Match this code on your phone</small>
                <strong>{handoff?.deviceCode}</strong>
              </div>
              <div className="handoff-ticket" aria-label="Sign-in handoff status">
                <div><small>01 · REQUEST</small><strong>This screen</strong></div>
                <span className="handoff-ticket__route" aria-hidden="true"><i /><i /><i /></span>
                <div><small>02 · APPROVE</small><strong>Your phone</strong></div>
                <span className="handoff-ticket__route" aria-hidden="true"><i /><i /><i /></span>
                <div><small>03 · OPEN</small><strong>Automatically</strong></div>
              </div>
              <button type="button" className="antiek-login__quiet" onClick={() => setEmailStatus("idle")}>
                Use a different email
              </button>
            </div>
          ) : (
            <>
              <div className="antiek-login__eyebrow"><span /> First unlock</div>
              <h1>Open your desk.</h1>
              <p className="antiek-login__lede">
                Start here, approve on your phone. This screen opens itself—no link gymnastics.
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

      <aside className="antiek-login__dispatch" aria-label="How device handoff works">
        <div className="dispatch-sheet">
          <header><span>ANTIEK / ACCESS DESK</span><span>PRIVATE</span></header>
          <p className="dispatch-sheet__number">№ 001</p>
          <h2>The email moves.<br />Your work doesn’t.</h2>
          <div className="dispatch-diagram" aria-hidden="true">
            <span className="dispatch-device">DESK</span><span className="dispatch-line" /><span className="dispatch-device dispatch-device--sun">PHONE</span><span className="dispatch-line dispatch-line--return" /><span className="dispatch-device">OPEN</span>
          </div>
          <p className="dispatch-sheet__note">A one-time approval returns securely to the screen that asked for it.</p>
          <footer><span>Expires in 15 min</span><span>No password stored</span></footer>
        </div>
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
